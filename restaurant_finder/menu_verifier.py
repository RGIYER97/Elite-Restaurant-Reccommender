"""Verify review-derived dish names against official online menus."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import ipaddress
import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests

from .http_utils import build_retrying_session


MAX_DOCUMENT_BYTES = 2_500_000
MAX_REDIRECTS = 3
MAX_MENU_PAGES = 5
MENU_HINT = re.compile(
    r"\b(menu|menus|food|drink|drinks|cocktail|cocktails|order|ordering)\b",
    re.IGNORECASE,
)
NON_MENU_HINT = re.compile(r"\b(gift|rewards?|careers?|jobs?)\b", re.IGNORECASE)
GENERIC_MENU_CATEGORIES = {
    "appetizer",
    "appetizers",
    "cocktail",
    "cocktails",
    "dessert",
    "desserts",
    "drink",
    "drinks",
    "entree",
    "entrees",
    "pastries",
    "sandwiches",
    "specials",
}


@dataclass(frozen=True, slots=True)
class MenuVerification:
    dishes: tuple[str, ...] = ()
    menu_url: str | None = None
    checked: bool = False


@dataclass(frozen=True, slots=True)
class _MenuDocument:
    url: str
    text: str


def _safe_https_url(url: str) -> bool:
    """Reject executable schemes, credentials, and explicit private IP targets."""

    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            return False
        hostname = parsed.hostname.casefold()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            return False
        try:
            return not ipaddress.ip_address(hostname).is_private
        except ValueError:
            return True
    except (TypeError, ValueError):
        return False


def _upgrade_to_https(url: str) -> str | None:
    """Upgrade legacy HTTP links without ever making a plaintext request."""

    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        upgraded = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        return upgraded if _safe_https_url(upgraded) else None
    except (TypeError, ValueError):
        return None


def _normalized(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold())).strip()


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _dish_appears(dish: str, menu_text: str) -> bool:
    return _menu_item_match(dish, menu_text) is not None


def _menu_item_match(dish: str, menu_text: str) -> str | None:
    """Return the first concise, canonical menu line matching a review phrase."""

    dish_normalized = _normalized(dish)
    if not dish_normalized or dish_normalized in GENERIC_MENU_CATEGORIES:
        return None

    # Menu formatting often separates a protein and preparation with punctuation
    # or changes singular/plural. Require every meaningful token on one concise
    # item-name line; long descriptive prose is not accepted as an item name.
    dish_tokens = {_stem(token) for token in dish_normalized.split() if len(token) > 2}
    if not dish_tokens:
        return None
    for line in menu_text.splitlines():
        item_name = " ".join(line.split()).strip()
        item_name = re.split(r"\s*\$\s*\d", item_name, maxsplit=1)[0].strip(" .·-")
        if not item_name or len(item_name) > 80 or len(item_name.split()) > 10:
            continue
        line_normalized = _normalized(item_name)
        line_tokens = {_stem(token) for token in line_normalized.split()}
        if dish_tokens.issubset(line_tokens):
            return item_name
    return None


class MenuVerifier:
    """Follow menu links from a Google-provided official website and match dishes."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 12,
    ) -> None:
        self.session = session or build_retrying_session()
        self.timeout_seconds = timeout_seconds

    def verify(self, website_url: str | None, dishes: tuple[str, ...]) -> MenuVerification:
        if not website_url or not dishes:
            return MenuVerification()
        website_url = _upgrade_to_https(website_url)
        if website_url is None:
            return MenuVerification()

        homepage = self._fetch(website_url)
        if homepage is None:
            return MenuVerification()

        documents: list[_MenuDocument] = []
        links: list[str] = []
        content_type, content = homepage
        if "pdf" in content_type:
            text = self._pdf_text(content)
            if self._usable_menu_text(text):
                documents.append(_MenuDocument(website_url, text))
        elif "html" in content_type:
            soup = BeautifulSoup(content, "html.parser")
            homepage_text = self._html_text(soup)
            if self._looks_like_menu_page(website_url, soup) and self._usable_menu_text(
                homepage_text
            ):
                documents.append(_MenuDocument(website_url, homepage_text))
            links = self._menu_links(website_url, soup)

        for link in links[:MAX_MENU_PAGES]:
            fetched = self._fetch(link)
            if fetched is None:
                continue
            page_type, page_content = fetched
            if "pdf" in page_type:
                text = self._pdf_text(page_content)
            else:
                page_soup = BeautifulSoup(page_content, "html.parser")
                if not self._looks_like_menu_page(link, page_soup):
                    continue
                text = self._html_text(page_soup)
            if self._usable_menu_text(text):
                documents.append(_MenuDocument(link, text))

        verified: list[str] = []
        first_source: str | None = None
        for dish in dishes:
            match = next(
                (
                    (doc.url, item_name)
                    for doc in documents
                    if (item_name := _menu_item_match(dish, doc.text)) is not None
                ),
                None,
            )
            if match:
                source, item_name = match
                if item_name.casefold() not in {item.casefold() for item in verified}:
                    verified.append(item_name)
                first_source = first_source or source

        return MenuVerification(
            dishes=tuple(verified),
            menu_url=first_source or (documents[0].url if documents else None),
            checked=bool(documents),
        )

    def _fetch(self, initial_url: str) -> tuple[str, bytes] | None:
        url = initial_url
        for _ in range(MAX_REDIRECTS + 1):
            if not _safe_https_url(url):
                return None
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException:
                return None

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    return None
                upgraded_redirect = _upgrade_to_https(urljoin(url, location))
                if upgraded_redirect is None:
                    return None
                url = upgraded_redirect
                continue
            if response.status_code != 200:
                return None
            content_length = response.headers.get("Content-Length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_DOCUMENT_BYTES:
                return None
            content = response.content
            if len(content) > MAX_DOCUMENT_BYTES:
                return None
            content_type = response.headers.get("Content-Type", "").casefold()
            if "html" not in content_type and "pdf" not in content_type:
                return None
            return content_type, content
        return None

    @staticmethod
    def _looks_like_menu_page(url: str, soup: BeautifulSoup) -> bool:
        path_hint = urlsplit(url).path.replace("-", " ").replace("_", " ")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        structured = bool(
            re.search(r'"@type"\s*:\s*"Menu(?:Item)?"', str(soup), re.IGNORECASE)
        )
        return bool(MENU_HINT.search(f"{path_hint} {title}")) or structured

    @staticmethod
    def _menu_links(base_url: str, soup: BeautifulSoup) -> list[str]:
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            label = anchor.get_text(" ", strip=True)
            hint_text = f"{label} {href.replace('-', ' ').replace('_', ' ')}"
            if NON_MENU_HINT.search(hint_text) or not MENU_HINT.search(hint_text):
                continue
            resolved = _upgrade_to_https(urljoin(base_url, href))
            if resolved and resolved not in links:
                links.append(resolved)
        return links

    @staticmethod
    def _html_text(soup: BeautifulSoup) -> str:
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        return soup.get_text("\n", strip=True)

    @staticmethod
    def _usable_menu_text(text: str) -> bool:
        """Ignore empty client-rendered shells and image-only menu placeholders."""

        return len(_normalized(text)) >= 100

    @staticmethod
    def _pdf_text(content: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:30])
        except Exception:  # malformed/encrypted third-party PDFs are simply unusable
            return ""

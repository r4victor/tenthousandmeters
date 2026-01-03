import datetime
import itertools
import json
import logging
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import feedparser
import requests
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
LINKS_DIR = os.path.join(PARENT_DIR, "content", "links")
FEEDS_FILE = "feeds.json"

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
JINJA_ENV = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)


@dataclass
class Feed:
    url: str
    content: str


@dataclass
class Link:
    domain: str
    title: str
    url: str
    published: datetime.datetime
    num: int


def update_links():
    feeds_urls = get_feeds_urls()
    feeds = get_feeds(feeds_urls)
    rendered_pages = render_pages_from_feeds(feeds)
    write_pages(rendered_pages)


def get_feeds_urls() -> list[str]:
    with open(os.path.join(BASE_DIR, FEEDS_FILE)) as f:
        return json.load(f)


def get_feeds(feeds_urls: list[str]) -> list[Feed]:
    with ThreadPoolExecutor(20) as p:
        feeds = p.map(get_feed, feeds_urls)
    return [feed for feed in feeds if feed is not None]


def get_feed(feed_url: str) -> Feed | None:
    try:
        response = requests.get(feed_url)
    except requests.exceptions.RequestException:
        logging.warning(f"Cannot get feed: {feed_url}")
        return None
    return Feed(url=feed_url, content=response.text)


def render_pages_from_feeds(feeds: list[Feed]) -> list[str]:
    links = get_links(feeds)
    pages = get_pages(links)
    return render_pages(pages)


def get_links(feeds: list[Feed]) -> list[Link]:
    return [link for feed in feeds for link in get_links_from_feed(feed)]


def get_links_from_feed(feed: Feed) -> list[Link]:
    feed_dict = feedparser.parse(feed.content)

    if feed_dict.bozo:
        # Handles only bad-formed XML.
        # We handle incomplete feeds ourselves.
        logging.warning(f"Invalid feed: {feed.url}\n{feed_dict.bozo_exception}")
        return []
    if not valid_feed(feed_dict):
        return []

    domain = get_domain(feed_dict.feed.link)
    links = [get_link_from_feed_entry(domain, e) for e in feed_dict.entries]
    return filter_bad_links(links)


def valid_feed(feed_dict: feedparser.FeedParserDict) -> bool:
    if "link" not in feed_dict.feed:
        logging.warning(f'Feed has no "link" attribute: {feed_dict}')
        return False
    if not all(valid_entry(entry) for entry in feed_dict.entries):
        return False
    return True


def valid_entry(feed_entry: feedparser.FeedParserDict) -> bool:
    for k in ("title", "link"):
        if k not in feed_entry:
            logging.warning(f'Feed entry missing "{k}" attribute: {feed_entry}')
            return False
    if "updated" not in feed_entry:
        # 'updated' is required but we tolerate it if 'published' is present
        if "published" not in feed_entry:
            logging.warning(
                f'Feed entry missing both "updated" and "published": {feed_entry}'
            )
    return True


def get_domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def get_link_from_feed_entry(
    source_domain: str, feed_entry: feedparser.FeedParserDict
) -> Link:
    return Link(
        domain=source_domain,
        title=feed_entry.title,
        url=feed_entry.link,
        published=get_published_date(feed_entry),
        num=0,
    )


def get_published_date(feed_entry: feedparser.FeedParserDict) -> datetime.datetime:
    # https://feedparser.readthedocs.io/en/latest/reference-entry-updated_parsed.html
    published = None
    if "updated" in feed_entry:
        published = feed_entry.updated_parsed
    if "published" in feed_entry:
        published = feed_entry.published_parsed
    return struct_time_to_datetime(published)


def struct_time_to_datetime(struct_time: time.struct_time) -> datetime.datetime:
    return datetime.datetime(*struct_time[:5])


def filter_bad_links(links: list[Link]) -> list[Link]:
    """
    Get rid of bad links (e.g. titles are too long).
    Jinja will take care of autoescaping html.
    """
    return [link for link in links if verify_link(link)]


def verify_link(
    link: Link, max_title_len: int = 200, max_domain_len: int = 200
) -> bool:
    if not 1 <= len(link.domain) <= max_domain_len:
        logging.warning(f'Bad "domain" length: {link}')
        return False
    if not 1 <= len(link.title) <= max_title_len:
        logging.warning(f'Bad "title" length: {link}')
        return False
    return True


def get_pages(links: list[Link]) -> list[dict[str, list[Link]]]:
    sorted_links = sort_links(links)
    links_by_pages = group_links_by_pages(sorted_links)
    pages = [group_links_by_date(page_links) for page_links in links_by_pages]
    return pages


def sort_links(links: list[Link]) -> list[Link]:
    sorted_links = sorted(links, key=lambda link: link.published, reverse=True)
    for i, link in enumerate(sorted_links, start=1):
        link.num = i
    return sorted_links


def group_links_by_pages(
    links: list[Link], links_per_page: int = 30
) -> list[list[Link]]:
    links_by_pages = []
    last_link = 0
    while last_link < len(links):
        links_by_pages.append(links[last_link : last_link + links_per_page])
        last_link += links_per_page
    return links_by_pages


def group_links_by_date(links: list[Link]) -> dict[str, list[Link]]:
    groups = itertools.groupby(links, key=lambda link: link.published.date())
    return {date.strftime("%B %-d, %-Y"): list(g) for date, g in groups}


def render_pages(pages: list[dict[str, list[Link]]]) -> list[str]:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    rendered_pages = []
    for i, link_groups in enumerate(pages, start=1):
        rendered_pages.append(render_page(i, link_groups, pages, now))
    return rendered_pages


def render_page(
    page_num: int,
    link_groups: dict[str, list[Link]],
    pages: list[dict[str, list[Link]]],
    updated: datetime.datetime,
) -> str:
    if page_num == 1:
        template = JINJA_ENV.get_template("links-page-1.md.jinja2")
        prev = None
    else:
        template = JINJA_ENV.get_template("links-page-n.md.jinja2")
        prev = f"{{filename}}/links/page-{page_num - 1}.md"
    if page_num < len(pages):
        next = f"{{filename}}/links/page-{page_num + 1}.md"
    else:
        next = None
    return template.render(
        {
            "page_num": page_num,
            "link_groups": link_groups,
            "pages_total": len(pages),
            "prev": prev,
            "next": next,
            "updated": f"{updated:%Y-%m-%d %H:%M} UTC",
        }
    )


def write_pages(rendered_pages: list[str]):
    if not os.path.exists(LINKS_DIR):
        os.mkdir(LINKS_DIR)

    for i, rendered_page in enumerate(rendered_pages, start=1):
        with open(os.path.join(LINKS_DIR, f"page-{i}.md"), "w+") as f:
            f.write(rendered_page)


if __name__ == "__main__":
    update_links()

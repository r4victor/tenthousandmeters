import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import datetime
import itertools
import json
import os
import urllib.parse

import feedparser
from jinja2 import Environment, FileSystemLoader
import requests


BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
LINKS_DIR = os.path.join(PARENT_DIR, 'content', 'links')
FEEDS_FILE = 'feeds.json'

TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=True
)


def update_links():
    feeds_urls = get_feeds_urls()
    feeds = get_feeds(feeds_urls)
    rendered_pages = render_pages_from_feeds(feeds)
    write_pages(rendered_pages)


def get_feeds_urls():
    with open(os.path.join(BASE_DIR, FEEDS_FILE)) as f:
        return json.load(f)


def get_feeds(feeds_urls):
    with ThreadPoolExecutor(100) as p:
        return list(p.map(get_feed, feeds_urls))


def get_feed(feed_url):
    return requests.get(feed_url).text


def render_pages_from_feeds(feeds):
    links = get_links(feeds)
    pages = get_pages(links)
    return render_pages(pages)


def get_links(feeds):
    return [link for feed in feeds for link in get_links_from_feed(feed)]


def get_links_from_feed(feed):
    feed_dict = feedparser.parse(feed)
    domain = get_domain(feed_dict.feed.link)
    links = [get_link_from_feed_entry(domain, e) for e in feed_dict.entries]
    return filter_bad_links(links)


def get_domain(url):
    return urllib.parse.urlparse(url).netloc


def get_link_from_feed_entry(source_domain, feed_entry):
    return {
        'domain': source_domain,
        'title': feed_entry.title,
        'url': feed_entry.link,
        'published': get_published_date(feed_entry)
    }


def get_published_date(feed_entry):
    published = feed_entry.updated_parsed
    if 'published' in feed_entry:
        published = feed_entry.published_parsed

    return struct_time_to_datetime(published)


def struct_time_to_datetime(struct_time):
    return datetime.datetime(*struct_time[:5])


def filter_bad_links(links):
    """
    Get rid of bad links (e.g. titles are too long).
    Jinja will take care of autoescaping html.
    """
    return [link for link in links if verify_link(link)]


def verify_link(link, max_title_len=200, max_domain_len=200):
    if not 1 <= len(link['domain']) <= max_domain_len:
        return False
    if not 1 <= len(link['title']) <= max_title_len:
        return False
    return True


def get_pages(links):
    sorted_links = sort_links(links)
    links_by_pages = group_links_by_pages(sorted_links)
    pages = [group_links_by_date(page_links) for page_links in links_by_pages]
    return pages


def sort_links(links):
    sorted_links = sorted(links, key=lambda l: l['published'], reverse=True)
    for i, link in enumerate(sorted_links, start=1):
        link['num'] = i
    return sorted_links


def group_links_by_pages(links, links_per_page=30):
    links_by_pages = []
    last_link = 0
    while last_link < len(links):
        links_by_pages.append(links[last_link:last_link+links_per_page])
        last_link += links_per_page
    return links_by_pages


def group_links_by_date(links):
    groups = itertools.groupby(links, key=lambda l: l['published'].date())
    return {date.strftime('%B %-d, %-Y'): list(g) for date, g in groups}


def render_pages(pages):
    now = datetime.datetime.utcnow()
    rendered_pages = []
    for i, link_groups in enumerate(pages, start=1):
        rendered_pages.append(render_page(i, link_groups, pages, now))
    return rendered_pages


def render_page(page_num, link_groups, pages, updated):
    if page_num == 1:
        template = JINJA_ENV.get_template('links-page-1.md.jinja2')
        prev = None
    else:
        template = JINJA_ENV.get_template('links-page-n.md.jinja2')
        prev = f'{{filename}}/links/page-{page_num-1}.md'

    if page_num < len(pages):
        next = f'{{filename}}/links/page-{page_num+1}.md'
    else:
        next = None

    return template.render({
        'page_num': page_num,
        'link_groups': link_groups,
        'pages_total': len(pages),
        'prev': prev,
        'next': next,
        'updated': f'{updated:%Y-%m-%d %H:%M} UTC',
    })


def write_pages(rendered_pages):
    if not os.path.exists(LINKS_DIR):
        os.mkdir(LINKS_DIR)

    for i, rendered_page in enumerate(rendered_pages, start=1):
        with open(os.path.join(LINKS_DIR, f'page-{i}.md'), 'w+') as f:
            f.write(rendered_page)


if __name__ == '__main__':
    update_links()

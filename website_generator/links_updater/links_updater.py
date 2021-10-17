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
JINJA_ENV = Environment(loader=FileSystemLoader(TEMPLATES_DIR))


def update_links():
    feeds_urls = get_feeds_urls()
    feeds = get_feeds(feeds_urls)
    update_links_from_feeds(feeds)


def get_feeds_urls():
    with open(os.path.join(BASE_DIR, FEEDS_FILE)) as f:
        return json.load(f)


def get_feeds(feeds_urls):
    return [get_feed(feed_url) for feed_url in feeds_urls]


def get_feed(feed_url):
    return requests.get(feed_url).text


def update_links_from_feeds(feeds):
    links = get_links(feeds)
    pages = get_pages(links)
    publish_pages(pages)


def get_links(feeds):
    return [link for feed in feeds for link in get_links_from_feed(feed)]


def get_links_from_feed(feed):
    feed_dict = feedparser.parse(feed)
    domain = get_domain(feed_dict.feed.link)
    return [get_link_from_feed_entry(domain, e) for e in feed_dict.entries]


def get_domain(url):
    return urllib.parse.urlparse(url).netloc


def get_link_from_feed_entry(source_domain, feed_entry):
    published = feed_entry.updated_parsed
    if 'published' in feed_entry:
        published = feed_entry.published_parsed

    return {
        'domain': source_domain,
        'title': feed_entry.title,
        'url': feed_entry.link,
        'published': struct_time_to_datetime(published)
    }


def get_published_date(feed_entry):
    published = feed_entry.updated_parsed
    if 'published' in feed_entry:
        published = feed_entry.published_parsed

    return struct_time_to_datetime(published)


def struct_time_to_datetime(struct_time):
    return datetime.datetime(*struct_time[:5])


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


def publish_pages(pages):
    if not os.path.exists(LINKS_DIR):
        os.makedirs(LINKS_DIR)
    now = datetime.datetime.utcnow()

    for i, link_groups in enumerate(pages, start=1):
        content = render_page(i, link_groups, pages, now)
        with open(os.path.join(LINKS_DIR, f'page-{i}.md'), 'w+') as f:
            f.write(content)


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


if __name__ == '__main__':
    update_links()

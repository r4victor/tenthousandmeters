import datetime
import os

import pytest

import links_updater


BASE_DIR = os.path.dirname(os.path.realpath(__file__))
SAMPLE_FEEDS_DIR = 'sample_feeds'


@pytest.fixture(scope='session')
def sample_feeds():
    filenames = ['atom1.0.xml']
    filepaths = [
        os.path.join(BASE_DIR, SAMPLE_FEEDS_DIR, filename)
        for filename in filenames
    ]
    feeds = []
    for filepath in filepaths:
        with open(filepath) as f:
            feeds.append(f.read())
    return feeds


def load_feed(filename):
    filepath = os.path.join(BASE_DIR, SAMPLE_FEEDS_DIR, filename)
    with open(filepath) as f:
        return f.read()


@pytest.fixture(scope='session')
def atom_feed():
    return load_feed('atom1.0.xml')


@pytest.fixture(scope='session')
def malicious_feed():
    return load_feed('malicious.xml')


@pytest.fixture(scope='session')
def incomplete_feed():
    return load_feed('incomplete.xml')


@pytest.fixture(scope='session')
def bad_url_feed():
    return load_feed('bad_url.xml')


def test_get_feeds_bad_url():
    feed_url = 'http://badurl'
    feeds = links_updater.get_feeds([feed_url])
    assert feeds == []


def test_render_empty_feed():
    feed = ''
    rendered_pages = links_updater.render_pages_from_feeds([feed])
    assert rendered_pages == []


def test_render_incomplete_feed(incomplete_feed):
    feed = incomplete_feed
    rendered_pages = links_updater.render_pages_from_feeds([feed])
    assert rendered_pages == []


def test_render_malicious_feed(malicious_feed):
    feed = malicious_feed
    rendered_pages = links_updater.render_pages_from_feeds([feed])
    assert rendered_pages == []


def test_render_bad_url_feed(bad_url_feed):
    feed = bad_url_feed
    rendered_pages = links_updater.render_pages_from_feeds([feed])
    assert rendered_pages == []


def test_get_links_from_good_feed(atom_feed):
    links = links_updater.get_links_from_feed(atom_feed)
    assert len(links) == 2
    for link in links:
        assert 'domain' in link
        assert 'title' in link
        assert 'url' in link
        assert 'published' in link

    assert links[0]['domain'] == 'example.org'
    assert links[0]['title'] == 'Entry 1'
    assert links[0]['url'] == 'http://example.org/entry1'
    assert links[0]['published'] == datetime.datetime(2003, 12, 13, 18, 30)


@pytest.mark.parametrize(
    'bad_feed', ['', '<just., non-sense', ]
)
def test_get_links_from_bad_feed(bad_feed):
    links = links_updater.get_links_from_feed(bad_feed)
    assert links == []


def test_group_links_by_pages():
    links = [{
        'domain': 'example.org',
        'title': f'link {i}',
        'url': 'http://example.org/link1',
        'published': datetime.datetime(2003, 1, 1, 18, i)
    } for i in range(1, 9)]
    pages = links_updater.group_links_by_pages(links, links_per_page=3)
    assert len(pages[0]) == 3
    assert len(pages[1]) == 3
    assert len(pages[2]) == 2


def test_bad_links_are_filtered():
    links = [{
        'domain': 'example.org',
        'title': 'link1',
        'url': 'http://example.org/linkok',
        'published': datetime.datetime(2003, 1, 1, 18, 1)
    }, {
        'domain': 'example.org',
        'title': '',  # no title is bad
        'url': 'http://example.org/linkok',
        'published': datetime.datetime(2003, 1, 1, 18, 1)
    }, {
        'domain': 'example.org',
        'title': 'bad title' * 100,
        'url': 'http://example.org/linkbad',
        'published': datetime.datetime(2003, 1, 1, 18, 2)
    }, {
        'domain': 'baddomain.org' * 100,
        'title': 'link 1',
        'url': 'http://example.org/linkbad',
        'published': datetime.datetime(2003, 1, 1, 18, 2)
    }]
    filtered_links = links_updater.filter_bad_links(links)
    assert filtered_links == links[:1]

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


@pytest.fixture
def atom_feed():
    filename = 'atom1.0.xml'
    filepath = os.path.join(BASE_DIR, SAMPLE_FEEDS_DIR, filename)
    with open(filepath) as f:
        return f.read()


def test_get_links_from_feed(atom_feed):
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



# def test():
#     print(links_updater.update_links())
#     assert False

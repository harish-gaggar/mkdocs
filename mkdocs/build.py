#coding: utf-8

from mkdocs.utils import copy_file, write_file, get_html_path
import collections
import jinja2
import markdown
import os
import re


TOC_LINK_REGEX = re.compile('<a href=["]([^"]*)["]>([^<]*)</a>')


class NavItem(object):
    def __init__(self, title, url, children=None):
        self.title, self.url = title, url
        self.children = children or []
        self.active = False


class PathToURL(object):
    def __init__(self, config):
        self.config = config

    def __call__(self, match):
        # TODO: This isn't quite right - we shouldn't blat relative paths with
        # absolute ones.
        path = match.groups()[0]
        return 'a href="%s"' % path_to_url(path, self.config)


def build_theme(config):
    """
    Copies the theme files into the build directory.
    """
    for (source_dir, dirnames, filenames) in os.walk(config['theme_dir']):
        relative_path = os.path.relpath(source_dir, config['theme_dir'])
        output_dir = os.path.normpath(os.path.join(config['build_dir'], relative_path))

        for filename in filenames:
            if not filename.endswith('.html'):
                source_path = os.path.join(source_dir, filename)
                output_path = os.path.join(output_dir, filename)
                copy_file(source_path, output_path)


def build_statics(config):
    """
    Copies any documentation static files into the build directory.
    """
    for (source_dir, dirnames, filenames) in os.walk(config['docs_dir']):
        relative_path = os.path.relpath(source_dir, config['docs_dir'])
        output_dir = os.path.normpath(os.path.join(config['build_dir'], relative_path))

        for filename in filenames:
            if not filename.endswith('.md'):
                source_path = os.path.join(source_dir, filename)
                output_path = os.path.join(output_dir, filename)
                copy_file(source_path, output_path)


def build_pages(config):
    """
    Builds all the pages and writes them into the build directory.
    """
    nav = generate_nav(config)
    loader = jinja2.FileSystemLoader(config['theme_dir'])
    env = jinja2.Environment(loader=loader)

    for path, title in config['pages']:
        active_nav = set_nav_active(path, config, nav)
        url = path_to_url(path, config)
        previous_url, next_url = path_to_previous_and_next_urls(path, config)

        source_path = os.path.join(config['docs_dir'], path)
        output_path = os.path.join(config['build_dir'], get_html_path(path))

        # Get the markdown text
        source_content = open(source_path, 'r').read().decode('utf-8')

        # Prepend a table of contents marker for the TOC extension
        source_content = source_content + '<!-- STARTTOC -->\n\n[TOC]'

        # Generate the HTML from the markdown source
        md = markdown.Markdown(extensions=['meta', 'toc'])
        content = md.convert(source_content)
        meta = md.Meta

        # Strip out the generated table of contents
        (content, toc_html) = content.split('<!-- STARTTOC -->', 1)

        # Post process the generated table of contents into a data structure
        toc = generate_toc(toc_html)

        # Allow 'template:' override in md source files.
        if 'template' in meta:
            template = env.get_template(meta['template'][0])
        else:
            template = env.get_template('base.html')

        # Replace links ending in .md with links to the generated HTML instead
        content = re.sub(r'a href="([^"]*\.md)"', PathToURL(config), content)
        content = re.sub('<pre>', '<pre class="prettyprint well">', content)

        context = {
            'project_name': config['project_name'],
            'page_title': active_nav.title,
            'content': content,

            'toc': toc,
            'nav': nav,
            'meta': meta,
            'config': config,

            'url': url,
            'base_url': config['base_url'],
            'homepage_url': path_to_url('index.md', config),
            'previous_url': previous_url,
            'next_url': next_url,
        }
        output_content = template.render(context)

        write_file(output_content.encode('utf-8'), output_path)


def generate_toc(toc_html):
    """
    Given a table of contents string that has been automatically generated by
    the markdown library, parse it into a tree of NavItem instances.
    """
    depth = 0
    lines = toc_html.splitlines()[2:-2]
    parents = []
    ret = []
    for line in lines:
        match = TOC_LINK_REGEX.search(line)
        if match:
            href, title = match.groups()
            nav = NavItem(title, href)
            # Add the item to its parent if required.  If it is a topmost
            # item then instead append it to our return value.
            if parents:
                parents[-1].children.append(nav)
            else:
                ret.append(nav)
            # If this item has children, store it as the current parent
            if line.endswith('<ul>'):
                parents.append(nav)
        elif line.startswith('</ul>'):
            parents.pop()

    # For the table of contents, always mark the first element as active
    if ret:
        ret[0].active = True

    return ret


def generate_nav(config):
    """
    Given the config file, returns a tree of NavItem instances.
    """
    ret = []
    for path, title in config['pages']:
        url = path_to_url(path, config)
        title, sep, child_title = title.partition('/')
        title = title.strip()
        child_title = child_title.strip()
        if not child_title:
            # New top level nav item
            nav = NavItem(title=title, url=url, children=[])
            ret.append(nav)
        elif not ret or (ret[-1].title != title):
            # New second level nav item
            nav = NavItem(title=child_title, url=url, children=[])
            parent = NavItem(title=title, url=None, children=[nav])
            ret.append(parent)
        else:
            # Additional second level nav item
            nav = NavItem(title=child_title, url=url, children=[])
            ret[-1].children.append(nav)
    return ret


def set_nav_active(path, config, nav):
    """
    Given the current page, set a boolean active field on each of the nav
    items in the NavItem tree.

    Additionally this returns the active nav item.
    """
    url = path_to_url(path, config)
    active = None
    for nav_item in nav:
        if nav_item.url == url:
            nav_item.active = True
            active = nav_item
        else:
            nav_item.active = False

        for child in nav_item.children:
            if child.url == url:
                child.active = True
                nav_item.active = True
                active = child
            else:
                child.active = False

    return active


def path_to_url(path, config):
    """
    Given a relative path, determine its corresponding absolute URL.
    """
    if config['local_files']:
        path = get_html_path(path)
        url = path.replace(os.path.pathsep, '/')
        return config['base_url'] + '/' + url

    path = os.path.splitext(path)[0]
    url = path.replace(os.path.pathsep, '/')
    url = config['base_url'] + '/' + url
    if url == 'index' or url.endswith('/index'):
        return url.rstrip('index')
    return url + '/'


def path_to_previous_and_next_urls(path, config):
    """
    Given a relative path, determine its previous and next URLs.
    """
    paths = [path_item for path_item, title in config['pages']]
    idx = paths.index(path)

    if idx == 0:
        prev = None
    else:
        prev = path_to_url(paths[idx - 1], config)

    if idx + 1 >= len(paths):
        next = None
    else:
        next = path_to_url(paths[idx + 1], config)

    return (prev, next)


def build(config):
    """
    Perform a full site build.
    """
    build_theme(config)
    build_statics(config)
    build_pages(config)

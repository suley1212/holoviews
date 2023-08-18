"""
HoloViews can be used to build highly-nested data-structures
containing large amounts of raw data. As a result, it is difficult to
generate a readable representation that is both informative yet
concise.

As a result, HoloViews does not attempt to build representations that
can be evaluated with eval; such representations would typically be
far too large to be practical. Instead, all HoloViews objects can be
represented as tree structures, showing how to access and index into
your data.
"""

import re
import textwrap

import param

from param.ipython import ParamPager
from param.parameterized import bothmethod

from .util import group_sanitizer, label_sanitizer



class ParamFilter(param.ParameterizedFunction):
    """
    Given a parameterized object, return a proxy parameterized object
    holding only the parameters that match some filter criterion.

    A filter is supplied with the parameter name and the parameter
    object and must return a boolean. A regular expression filter has
    been supplied and may be used to search for parameters mentioning
    'bounds' as follows:

    filtered = ParamFilter(obj, ParamFilter.regexp_filter('bounds'))

    This may be used to filter documentation generated by param.
    """

    def __call__(self, obj, filter_fn=None):
        if filter_fn is None:
            return obj

        name = obj.__name__ if isinstance(obj,type) else obj.__class__.__name__
        class_proxy = type(name, (param.Parameterized,),
                      {k:v for k,v in obj.param.objects('existing').items()
                       if filter_fn(k,v)})

        if isinstance(obj,type):
            return class_proxy
        else:
            instance_params = obj.param.values().items()
            obj_proxy = class_proxy()
            filtered = {k:v for k,v in instance_params
                        if (k in obj_proxy.param)
                            and not obj_proxy.param.objects('existing')[k].constant}
            obj_proxy.param.update(**filtered)
            return obj_proxy

    @param.parameterized.bothmethod
    def regexp_filter(self_or_cls, pattern):
        """
        Builds a parameter filter using the supplied pattern (may be a
        general Python regular expression)
        """
        def inner_filter(name, p):
            name_match = re.search(pattern,name)
            if name_match is not None:
                return True
            if p.doc is not None:
                doc_match = re.search(pattern,p.doc)
                if doc_match is not None:
                    return True
            return False
        return inner_filter


class InfoPrinter:
    """
    Class for printing other information related to an object that is
    of use to the user.
    """
    headings = ['\x1b[1;35m%s\x1b[0m', '\x1b[1;32m%s\x1b[0m']
    ansi_escape = re.compile(r'\x1b[^m]*m')
    ppager = ParamPager()
    store = None
    elements = []

    @classmethod
    def get_parameter_info(cls, obj, ansi=False,  show_values=True,
                           pattern=None, max_col_len=40):
        """
        Get parameter information from the supplied class or object.
        """
        if cls.ppager is None: return ''
        if pattern is not None:
            obj = ParamFilter(obj, ParamFilter.regexp_filter(pattern))
            if len(list(obj.param)) <= 1:
                return None
        param_info = cls.ppager.get_param_info(obj)
        param_list = cls.ppager.param_docstrings(param_info)
        if not show_values:
            retval = cls.ansi_escape.sub('', param_list) if not ansi else param_list
            return cls.highlight(pattern, retval)
        else:
            info = cls.ppager(obj)
            if ansi is False:
                info = cls.ansi_escape.sub('', info)
            return cls.highlight(pattern, info)

    @classmethod
    def heading(cls, heading_text, char='=', level=0, ansi=False):
        """
        Turn the supplied heading text into a suitable heading with
        optional underline and color.
        """
        heading_color = cls.headings[level] if ansi else '%s'
        if char is None:
            return heading_color % f'{heading_text}\n'
        else:
            heading_ul = char*len(heading_text)
            return heading_color % f'{heading_ul}\n{heading_text}\n{heading_ul}'


    @classmethod
    def highlight(cls, pattern, string):
        if pattern is None: return string
        return re.sub(pattern, '\033[43;1;30m\\g<0>\x1b[0m',
                      string, flags=re.IGNORECASE)


    @classmethod
    def info(cls, obj, ansi=False, backend='matplotlib', visualization=True,
             pattern=None, elements=None):
        """
        Show information about an object in the given category. ANSI
        color codes may be enabled or disabled.
        """
        if elements is None:
            elements = []
        cls.elements = elements
        ansi_escape = re.compile(r'\x1b[^m]*m')

        isclass = isinstance(obj, type)
        name = obj.__name__ if isclass  else obj.__class__.__name__
        backend_registry = cls.store.registry.get(backend, {})
        plot_class = backend_registry.get(obj if isclass else type(obj), None)
        # Special case to handle PlotSelectors
        if hasattr(plot_class, 'plot_classes'):
            plot_class =  next(iter(plot_class.plot_classes.values()))


        if visualization is False or plot_class is None:
            if pattern is not None:
                obj = ParamFilter(obj, ParamFilter.regexp_filter(pattern))
                if len(list(obj.param)) <= 1:
                    return (f'No {name!r} parameters found matching specified pattern {pattern!r}')
            info = param.ipython.ParamPager()(obj)
            if ansi is False:
                info = ansi_escape.sub('', info)
            return cls.highlight(pattern, info)

        heading = name if isclass else f'{name}: {obj.group} {obj.label}'
        prefix = heading
        lines = [prefix, cls.object_info(obj, name, backend=backend, ansi=ansi)]

        if not isclass:
            lines += ['', cls.target_info(obj, ansi=ansi)]
        if plot_class is not None:
            lines += ['', cls.options_info(plot_class, ansi, pattern=pattern)]
        return "\n".join(lines)

    @classmethod
    def get_target(cls, obj):
        objtype=obj.__class__.__name__
        group = group_sanitizer(obj.group)
        label = ('.' + label_sanitizer(obj.label) if obj.label else '')
        target = f'{objtype}.{group}{label}'
        return (None, target) if hasattr(obj, 'values') else (target, None)


    @classmethod
    def target_info(cls, obj, ansi=False):
        if isinstance(obj, type): return ''

        targets = obj.traverse(cls.get_target)
        elements, containers = zip(*targets)
        element_set = {el for el in elements if el is not None}
        container_set = {c for c in containers if c is not None}

        element_info = None
        if len(element_set) == 1:
            element_info = f'Element: {next(iter(element_set))}'
        elif len(element_set) > 1:
            element_info = 'Elements:\n   %s'  % '\n   '.join(sorted(element_set))

        container_info = None
        if len(container_set) == 1:
            container_info = f'Container: {next(iter(container_set))}'
        elif len(container_set) > 1:
            container_info = 'Containers:\n   %s'  % '\n   '.join(sorted(container_set))
        heading = cls.heading('Target Specifications', ansi=ansi, char="-")

        target_header = '\nTargets in this object available for customization:\n'
        if element_info and container_info:
            target_info = f'{element_info}\n\n{container_info}'
        else:
            target_info = element_info if element_info else container_info

        target_footer = ("\nTo see the options info for one of these target specifications,"
                         "\nwhich are of the form {type}[.{group}[.{label}]], do holoviews.help({type}).")

        return f'{heading}\n{target_header}\n{target_info}\n{target_footer}'


    @classmethod
    def object_info(cls, obj, name, backend, ansi=False):
        element = not getattr(obj, '_deep_indexable', False)
        element_url ='http://holoviews.org/reference/elements/{backend}/{obj}.html'
        container_url ='http://holoviews.org/reference/containers/{backend}/{obj}.html'
        url = element_url if element else container_url
        link = url.format(obj=name, backend=backend)

        link = None if element and (name not in cls.elements) else link
        msg = ("\nOnline example: {link}" if link else ''
               + "\nHelp for the data object: holoviews.help({obj})"
               + " or holoviews.help(<{lower}_instance>)")

        return '\n'.join([msg.format(obj=name, lower=name.lower(), link=link)])


    @classmethod
    def options_info(cls, plot_class, ansi=False, pattern=None):
        if plot_class.style_opts:
            backend_name = plot_class.backend
            style_info = f"\n(Consult {backend_name}'s documentation for more information.)"
            style_keywords = f"\t{', '.join(plot_class.style_opts)}"
            style_msg = f'{style_keywords}\n{style_info}'
        else:
            style_msg = '\t<No style options available>'

        param_info = cls.get_parameter_info(plot_class, ansi=ansi, pattern=pattern)
        lines = [ cls.heading('Style Options', ansi=ansi, char="-"), '',
                  style_msg, '',
                  cls.heading('Plot Options', ansi=ansi, char="-"), '']
        if param_info is not None:
            lines += ["The plot options are the parameters of the plotting class:\n",
                      param_info]
        elif pattern is not None:
            lines+= [f'No {plot_class.__name__!r} parameters found matching specified pattern {pattern!r}.']
        else:
            lines+= [f'No {plot_class.__name__!r} parameters found.']

        return '\n'.join(lines)


class PrettyPrinter(param.Parameterized):
    """
    The PrettyPrinter used to print all HoloView objects via the
    pprint method.
    """

    show_defaults = param.Boolean(default=False, doc="""
        Whether to show default options as part of the repr.
        If show_options=False this has no effect.""")

    show_options = param.Boolean(default=False, doc="""
        Whether to show options as part of the repr.""")

    tab = '   '

    type_formatter= ':{type}'

    @bothmethod
    def pprint(cls_or_slf, node):
        return cls_or_slf.serialize(cls_or_slf.recurse(node))

    @bothmethod
    def serialize(cls_or_slf, lines):
        accumulator = []
        for level, line in lines:
            accumulator.append((level *cls_or_slf.tab) + line)
        return "\n".join(accumulator)

    @bothmethod
    def shift(cls_or_slf, lines, shift=0):
        return [(lvl+shift, line) for (lvl, line) in lines]

    @bothmethod
    def padding(cls_or_slf, items):
        return max(len(p) for p in items) if len(items) > 1 else len(items[0])

    @bothmethod
    def component_type(cls_or_slf, node):
        "Return the type.group.label dotted information"
        if node is None: return ''
        return cls_or_slf.type_formatter.format(type=str(type(node).__name__))

    @bothmethod
    def recurse(cls_or_slf, node, attrpath=None, attrpaths=None, siblings=None, level=0, value_dims=True):
        """
        Recursive function that builds up an ASCII tree given an
        AttrTree node.
        """
        if siblings is None:
            siblings = []
        if attrpaths is None:
            attrpaths = []
        level, lines = cls_or_slf.node_info(node, attrpath, attrpaths, siblings, level, value_dims)
        attrpaths = ['.'.join(k) for k in node.keys()] if  hasattr(node, 'children') else []
        siblings = [node.get(child) for child in attrpaths]
        for attrpath in attrpaths:
            lines += cls_or_slf.recurse(node.get(attrpath), attrpath, attrpaths=attrpaths,
                                 siblings=siblings, level=level+1, value_dims=value_dims)
        return lines

    @bothmethod
    def node_info(cls_or_slf, node, attrpath, attrpaths, siblings, level, value_dims):
        """
        Given a node, return relevant information.
        """
        opts = None
        if hasattr(node, 'children'):
            (lvl, lines) = (level, [(level, cls_or_slf.component_type(node))])
            opts = cls_or_slf.option_info(node)
        elif hasattr(node, 'main'):
            (lvl, lines) = cls_or_slf.adjointlayout_info(node, siblings, level, value_dims)
        elif getattr(node, '_deep_indexable', False):
            (lvl, lines) = cls_or_slf.ndmapping_info(node, siblings, level, value_dims)
        elif hasattr(node, 'unit_format'):
            (lvl, lines) = level, [(level, repr(node))]
        else:
            (lvl, lines) = cls_or_slf.element_info(node, siblings, level, value_dims)
            opts = cls_or_slf.option_info(node)

        # The attribute indexing path acts as a prefix (if applicable)
        if attrpath is not None:
            padding = cls_or_slf.padding(attrpaths)
            (fst_lvl, fst_line) = lines[0]
            line = '.'+attrpath.ljust(padding) +' ' + fst_line
            lines[0] = (fst_lvl, line)
        else:
            fst_lvl = level

        if cls_or_slf.show_options and opts and opts.kwargs:
            lines += [(fst_lvl, l) for l in cls_or_slf.format_options(opts)]
        return (lvl, lines)

    @bothmethod
    def element_info(cls_or_slf, node, siblings, level, value_dims):
        """
        Return the information summary for an Element. This consists
        of the dotted name followed by an value dimension names.
        """
        info = cls_or_slf.component_type(node)
        if len(node.kdims) >= 1:
            info += cls_or_slf.tab + f"[{','.join(d.name for d in node.kdims)}]"
        if value_dims and len(node.vdims) >= 1:
            info += cls_or_slf.tab + f"({','.join(d.name for d in node.vdims)})"
        return level, [(level, info)]

    @bothmethod
    def option_info(cls_or_slf, node):
        if not cls_or_slf.show_options:
            return None
        from .options import Store, Options
        options = {}
        for g in Options._option_groups:
            gopts = Store.lookup_options(Store.current_backend, node, g,
                                         defaults=cls_or_slf.show_defaults)
            if gopts:
                options.update(gopts.kwargs)
        opts = Options(**{k:v for k,v in options.items() if k != 'backend'})
        return opts

    @bothmethod
    def format_options(cls_or_slf, opts, wrap_count=100):
        opt_repr = str(opts)
        cls_name = type(opts).__name__
        indent = ' '*(len(cls_name)+1)
        wrapper = textwrap.TextWrapper(width=wrap_count, subsequent_indent=indent)
        return [' | '+l for l in wrapper.wrap(opt_repr)]

    @bothmethod
    def adjointlayout_info(cls_or_slf, node, siblings, level, value_dims):
        first_line = cls_or_slf.component_type(node)
        lines = [(level, first_line)]
        additional_lines = []
        for component in list(node.data.values()):
            additional_lines += cls_or_slf.recurse(component, level=level)
        lines += cls_or_slf.shift(additional_lines, 1)
        return level, lines

    @bothmethod
    def ndmapping_info(cls_or_slf, node, siblings, level, value_dims):
        key_dim_info = f"[{','.join(d.name for d in node.kdims)}]"
        first_line = cls_or_slf.component_type(node) + cls_or_slf.tab + key_dim_info
        lines = [(level, first_line)]

        opts = cls_or_slf.option_info(node)
        if cls_or_slf.show_options and opts and opts.kwargs:
            lines += [(level, l) for l in cls_or_slf.format_options(opts)]

        if len(node.data) == 0:
            return level, lines
        # .last has different semantics for GridSpace
        last = list(node.data.values())[-1]
        if last is not None and last._deep_indexable and not hasattr(last, 'children'):
            level, additional_lines = cls_or_slf.ndmapping_info(last, [], level, value_dims)
        else:
            additional_lines = cls_or_slf.recurse(last, level=level, value_dims=value_dims)
        lines += cls_or_slf.shift(additional_lines, 1)
        return level, lines


__all__ = ['PrettyPrinter', 'InfoPrinter']

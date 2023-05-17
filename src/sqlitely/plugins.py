"""
User-defined plugins functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool
Released under the MIT License.

@author      Erki Suurjaak
@created     05.05.2023
@modified    05.05.2023
------------------------------------------------------------------------------
"""
import copy
import inspect
import logging

import six

from . lib import util
from . import conf

logger = logging.getLogger(__name__)


## {category name: [{"body", "name", "target", "..}]}
PLUGINS = {}


def init_plugins(name):
    """
    Initializes plugins from configuration, compiling their code and validating namespace.

    @param   name     plugin category to initialize entries from, like "ValueEditorFunctions"
    """
    PLUGINS[name] = [copy.deepcopy(x) for x in conf.Plugins.get(name, [])]
    for item in PLUGINS[name]:
        if not isinstance(item.get("body"), six.text_type):
            item["body"] = str(item.get("body", ""))
        item.pop("target", None)
        ns, err = compile_plugin(item["body"])
        if err: logger.warning("Error compiling %r plugin: %s", name, err)
        if not ns: continue  # for item
        if callable(ns.get(item.get("name"))): item["target"] = ns[item["name"]]


def get_plugins(name):
    """
    Returns a list of initialized plugins under specified category.

    @param   name     plugin category to get initialized entries from, like "ValueEditorFunctions"
    @return           [{"name", "body", ?"target", ?"namespace", ..}]
    """
    if name not in PLUGINS: return []
    return [copy.copy(x) for x in PLUGINS[name]]


def set_plugins(name, plugins):
    """
    Sets plugins content and saves configuration.

    @param   name     plugin category to store entries under, like "ValueEditorFunctions"
    @param   plugins  list of {"name": callable name in eval namespace, body: Python code, ..}
    """
    PLUGINS[name][:] = plugins
    configs = [{k: v for k, v in x.items()
                if isinstance(v, six.string_types) or k == "active" and v is False}
               for x in plugins]
    conf.Plugins[name] = [x for x in configs if x]
    conf.save()


def compile_plugin(text):
    """
    @param   text  Python code as text
    @return        (resulting eval namespace or None), (None or error message)
    """
    result, err = {}, None
    try: eval(compile(text, "", "exec"), None, result)
    except Exception as e: result, err = None, str(e)
    return result, err


def validate_plugin(plugin, arity=None, cls=None):
    """
    Validates plugin code compiling and providing specified callable.

    @param   plugin  {"name": callable name in eval namespace, "body": Python code, ..}
    @param   arity   minimum number of arguments the callable must support
    @param   cls     class that the callable must be or extend, or a tuple of classes
    @return          {"name", "body", "target", "valid", ..}, (None or error message)
    """
    result = dict(plugin)
    ns, err = compile_plugin(plugin.get("body"))
    runnable = None if err else ns.get(plugin.get("name"))
    if err:
        pass
    elif not callable(runnable):
        err = "No callable named '%s' in code." % (plugin.get("name", ""))
    elif cls and not not issubclass(runnable, cls):
        err = "Callable '%s' not of type %s." % (plugin["name"], cls)
    elif arity is not None and util.get_arity(runnable) < arity:
        err = "Callable '%s' does not support %s arguments." % (plugin["name"], arity)
    else:
        result.update(target=runnable)
    return 


def validate_callable(runnable, arity=None, cls=None):
    """
    Validates plugin callable.

    @param   runnable  plugin callable
    @param   arity     minimum number of arguments the callable must support
    @param   cls       class that the callable must be or extend, or a tuple of classes
    @return            True or error message
    """
    err = None
    if not callable(runnable):
        err = "%r is not callable." % runnable
    elif cls and not isinstance(runnable, cls) \
    and not (inspect.isclass(runnable) and issubclass(runnable, cls)):
        err = "Callable %r not of type %s." % (runnable, cls)
    elif arity is not None:
        runnable_arity = util.get_arity(runnable)
        if runnable_arity >= 0 and runnable_arity < arity:
            err = "Callable %r does not support %s arguments." % (runnable, arity)
    return err or True

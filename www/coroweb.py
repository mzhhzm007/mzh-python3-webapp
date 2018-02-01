#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from apis import APIError


'''
#比如@get加在下面的函数上
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r
相当于signout=get('/signout')(signout)
此时调用了get装饰器，返回了decorator函数，再调用返回的这个decorator函数，参数是signout,即decorator(signout)
根据decorator(func)的定义，会返回一个wrapper函数，但是它没有调用，只有当signout(request)调用的时候，其实才会调用
wrapper函数，即调用wrapper(request)

wrapper.__method__ = 'GET'
wrapper.__route__ = path
这里wrapper添加了两个私有属性，在后续调用的时候，wrapper(*args, **kw)里面调用func(*args, **kw)，这两个属性也会加入
后面就可以获取这两个属性，一个是path一个是http请求方法
'''
def get(path):
    '''
    Define decorator @get('/path')
    '''

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper

    return decorator


def post(path):
    '''
    Define decorator @post('/path')
    '''

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper

    return decorator


'''
POSITIONAL_ONLY         位置参数，可能类似self这种参数，必须在第一位的
POSITIONAL_OR_KEYWORD   没有任何*声明，可以通过位置或者关键字传参
VAR_POSITIONAL          可变参数，通过*声明
KEYWORD_ONLY            命名关键字参数，这种参数只会在VAR_POSITIONAL类型参数（可变参数）的后面而且不带**前缀
                        用特殊分隔符*隔开，或者前面有可变参数的话，可以不加*
VAR_KEYWORD             关键字参数，**声明
'''
'''
POSITIONAL_OR_KEYWORD和KEYWORD_ONLY可以自定义默认参数
而VAR_POSITIONAL和VAR_KEYWORD不允许自定义默认参数的
因为VAR_POSITIONAL的默认参数是tuple()空元祖
而VAR_KEYWORD的默认参数是dict()空字典
'''

#获取没有默认参数的命名关键字参数，这些是需要调用的时候赋值的
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

#获取命名关键字参数
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

#判断是否有命名关键字参数
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

#判断是否有关键词参数
def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

#判断是否有request参数
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL
                      and param.kind != inspect.Parameter.KEYWORD_ONLY
                      and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                'request parameter must be the last named parameter in function: %s%s'
                % (fn.__name__, str(sig)))
    return found


class RequestHandler(object):
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request):
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded'
                                   ) or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest(
                        'Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning(
                        'Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))


def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(
            fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' %
                 (method, path, fn.__name__,
                  ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))


def add_routes(app, module_name):
    n = module_name.rfind('.')
    if n == (-1):
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n + 1:]
        mod = getattr(
            __import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)#这两个属性就是get和post的装饰器里加进去的
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)
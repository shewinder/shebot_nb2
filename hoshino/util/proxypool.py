import asyncio
import random
from typing import List

import aiohttp
import requests
from aiohttp import ClientResponse
from aiohttp.client_exceptions import (
    ClientConnectionError,
    ClientHttpProxyError,
    ClientProxyConnectionError,
    ClientOSError,
)
from ssl import SSLCertVerificationError
from requests import Response
from requests.api import request
from requests.exceptions import ProxyError, Timeout

PROXY_POOL_URL = "http://81.70.165.122:5555/max_score"

import asyncio


class ProxyException(Exception):
    pass


class TimeoutException(Exception):
    pass


class NetworkException(Exception):
    pass


class ProxyPool:
    def __init__(self, proxy_pool_url=PROXY_POOL_URL):
        self.proxies: List[str] = []
        self.proxy_pool_url = proxy_pool_url
        self.proxy_iterator = self.fetch_proxys()
        self.ok_cnt = 0
        self.fail_cnt = 0

    def fetch_proxys(self):
        all = requests.get(self.proxy_pool_url).text.split()
        for i in all:
            yield i

    def refresh(self):
        self.proxy_iterator = self.fetch_proxys()

    def get_proxy(self):
        if len(self.proxies) < 2:
            try:
                self.proxies.append(next(self.proxy_iterator))
            except StopIteration:
                self.refresh()
                self.proxies.append(next(self.proxy_iterator))
        if len(self.proxies) != 0:
            return random.choice(self.proxies)
        else:
            return None

    def put_proxy(self, proxy):
        self.proxies.append(proxy)

    def remove_proxy(self, proxy):
        try:
            self.proxies.remove(proxy)
        except ValueError:
            # in async mode, the proxy may have been removed by another coroutine
            pass


class RequestWithProxy(ProxyPool):
    def __init__(self, timeout: int = 3):
        super().__init__()
        self.timeout = timeout
        self.proxies = []

    def do(self, method: str, url: str, **kwargs) -> requests.Response:
        proxy = self.get_proxy()
        kwargs["proxies"] = {"http": "http://" + proxy, "https": "http://" + proxy}
        try:
            resp = request(method, url, **kwargs)
            self.ok_cnt += 1
            return resp
        except ProxyError:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise ProxyException("connect to proxy failed")
        except Timeout:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise TimeoutException
        except:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise

    def get(self, url, **kwargs) -> Response:
        r"""Sends a GET request.

        :param url: URL for the new :class:`Request` object.
        :param params: (optional) Dictionary, list of tuples or bytes to send
            in the query string for the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """
        kwargs.setdefault("allow_redirects", False)
        kwargs.setdefault("timeout", self.timeout)
        return self.do("get", url, **kwargs)

    def post(url, data=None, json=None, **kwargs) -> Response:
        r"""Sends a POST request.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json data to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """

        return request("post", url, data=data, json=json, **kwargs)


class AioRequestWithProxy(ProxyPool):
    def __init__(self, timeout: int = 3):
        super().__init__()
        self.proxies: List[str] = []
        self.timeout = timeout

    async def do(self, method: str, url: str, **kwargs) -> ClientResponse:
        proxy = self.get_proxy()
        kwargs["proxy"] = "http://" + proxy
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(
                timeout=timeout, trust_env=True
            ) as session:
                async with session.request(method, url, **kwargs) as resp:
                    await resp.read()
                    self.ok_cnt += 1
                    return resp
        except (ClientProxyConnectionError, ClientHttpProxyError):
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise ProxyException("connect to proxy failed")
        except (ClientConnectionError, ClientOSError, SSLCertVerificationError) as e:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise NetworkException(f"{e}")
        except asyncio.exceptions.TimeoutError:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise TimeoutException
        except ValueError as e:
            if (
                str(e) == "negative file descriptor"
            ):  # I cound not figure out what happened
                self.fail_cnt += 1
                self.remove_proxy(proxy)
                raise ProxyException(
                    "negative file descriptor (this is a exception i can not handle, so let it tepmporary as a proxy exception)"
                )
            else:
                raise
        except:
            self.remove_proxy(proxy)
            self.fail_cnt += 1
            raise

    async def get(self, url, **kwargs) -> ClientResponse:
        return await self.do("get", url, **kwargs)

    async def post(self, url, **kwargs) -> ClientResponse:
        return await self.do("post", url, **kwargs)


aioreq = AioRequestWithProxy()
req = RequestWithProxy()


def get(url, **kwargs) -> Response:
    return req.get(url, **kwargs)


def post(url, data=None, json=None, **kwargs) -> Response:
    return req.post(url, data=data, json=json, **kwargs)


async def aioget(url, **kwargs) -> ClientResponse:
    return await aioreq.get(url, **kwargs)


async def aiopost(url, **kwargs) -> ClientResponse:
    return await aioreq.post(url, **kwargs)


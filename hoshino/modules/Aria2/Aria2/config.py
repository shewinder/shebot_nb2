from pydantic import BaseModel


class Aria2Config(BaseModel):
    url: str
    token: str
    base_url: str
    local_path: str


config = {
    'url': 'http://81.70.165.122:6800/jsonrpc',
    'token': "426850",
    'base_url': "",
    'local_path': ""
}

aria2config = Aria2Config(**config)

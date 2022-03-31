from hoshino import sucmd, Bot
from hoshino.util import proxypool
showcmd = sucmd('proxypool status', aliases={'pool'})


@showcmd.handle()
async def show_avail_rate(bot: Bot):
    msg = ["AioHttpProxyPool:"]
    msg.append(f"success {proxypool.aioreq.ok_cnt}")
    msg.append(f"fail {proxypool.aioreq.fail_cnt}")
    if proxypool.aioreq.ok_cnt + proxypool.aioreq.fail_cnt > 0:
        msg.append(f'rate {proxypool.aioreq.ok_cnt/ (proxypool.aioreq.ok_cnt + proxypool.aioreq.fail_cnt):.2%}')
    msg.append('')
    msg.append('HttpProxyPool:')
    msg.append(f"success {proxypool.req.ok_cnt}")
    msg.append(f"fail {proxypool.req.fail_cnt}")
    if proxypool.req.ok_cnt + proxypool.req.fail_cnt > 0:
        msg.append(f'rate {proxypool.req.ok_cnt/ (proxypool.req.ok_cnt + proxypool.req.fail_cnt):.2%}')
    await showcmd.finish('\n'.join(msg))

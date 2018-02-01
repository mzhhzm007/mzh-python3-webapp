# import orm
# from models import User, Blog, Comment
# import asyncio
# loop = asyncio.get_event_loop()

import logging
logging.basicConfig(level=logging.INFO)
# async def test():
#     await orm.create_pool(
#         loop=loop,
#         host='127.0.0.1',
#         port=3306,
#         user='root',
#         password='atc#2345',
#         db='snowing')
#     u = User(
#         name='Test',
#         email='test@example.com',
#         passwd='1234567890',
#         image='about:blank',
#         id="123")
#     await u.save()


# #把协程丢到事件循环中执行
# loop.run_until_complete(test())
def consumer():
    r = ''
    while True:
        nn = yield r
        if not nn:
            return
        logging.info('[CONSUMER] Consuming %s...' % nn)
        r = '200 OK'

def produce(c):
    c.send(None)
    n = 0
    while n < 5:
        n = n + 1
        print('[PRODUCER] Producing %s...' % n)
        r = c.send(n)
        logging.info('[PRODUCER] Consumer return: %s' % r)
    c.close()

c = consumer()
produce(c)
import asyncio
import functools
import logging
import os
import signal

import aioredis
import aiotg

from utils import Config
from commands.boss import set_boss, botta, lista_botta
from commands.riddle_solvers import wordsolver
from commands.dungeon import set_dungeon, log_user_action, log_user_position, log_user_direction, close_dungeon, get_map
from button_callbacks import gabbia_buttons_reply, gabbia_choice, maps_button_reply_phase1, maps_choice_phase1
from deco import restricted, setup_coro
from background import update_group_members, update_items_name, build_maps


logging.basicConfig(
    format='%(asctime)s %(name)-12s %(levelname)-8s %(funcName)s:%(message)s',
    level=logging.INFO)
logger = logging.getLogger('bot')


async def stop_loop(loop, redis):
    await asyncio.sleep(0.05)
    redis.close()
    await redis.wait_closed()
    loop.stop()


def clean_shutdown(loop, signame, redis):
    logger.warning(f'{signame} received, stopping!')
    for t in asyncio.Task.all_tasks():
        t.cancel()
    loop.create_task(stop_loop(loop, redis))


def add_signal_handlers(loop, redis):
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame),
                                functools.partial(clean_shutdown, loop, signame, redis))
    logger.info(f"pid {os.getpid()}: send SIGINT or SIGTERM to exit.")


def create_bot(redis):
    bot = aiotg.Bot(Config.TOKEN, name=Config.NAME)

    restricted_deco = restricted(redis)
    commands = [
        (set_boss, r'^/setboss'),
        (botta, r'^/botta'),
        (lista_botta, r'^/listabotta'),
        (wordsolver, r'^Sul portone del rifugio vi è una piccola pulsantiera'),
        (gabbia_buttons_reply, r'^Attenzione! Appena messo piede nella stanza'),
        (maps_button_reply_phase1, '^/mappe'),
        (set_dungeon, r'^Sei stato aggiunto alla Lista Avventurieri del dungeon (.*)!'),
        (close_dungeon, '^/quitdg'),
        (get_map, '^/mappa'),
        (log_user_position, r'Stanza (\d+)/(\d+)'),
        (log_user_direction, rf"({Config.ARROW_UP}|{Config.ARROW_LEFT}|{Config.ARROW_RIGHT})"),
        # (set_alert, r'^/setalert'),
        # (unset_alert, r'^/unsetalert'),
        # (show_alerts, r'^/showalerts'),
    ]
    dungeon_commands = [(log_user_action, '^'+string) for string in Config.DUNGEONS_RE]
    commands += dungeon_commands

    callbacks = [
        (gabbia_choice, 'gabbiaclick-(\w+|\d+)'),
        (maps_choice_phase1, 'maps1click-(\w)')
    ]

    for fn, re in commands:
        bot.add_command(re, restricted_deco(fn))
    for fn, re in callbacks:
        bot.add_callback(re, restricted_deco(fn))

    return bot


def create_tasks(loop, redis):
    bot = create_bot(redis)

    coroutines = [
        setup_coro(bot.loop())(),
        update_group_members(bot, redis),
        update_items_name(bot, redis),
        build_maps(bot, redis)]

    for coro in coroutines:
        loop.create_task(coro)


def run_bot():
    loop = asyncio.get_event_loop()

    logger.info('creating redis connection')
    redis_conn = loop.run_until_complete(aioredis.create_redis(('localhost', 6379), encoding="utf-8"))

    logger.info('adding signal handlers')
    add_signal_handlers(loop, redis_conn)

    logger.info('creating tasks: bot and background coros')
    create_tasks(loop, redis_conn)

    try:
        logger.info('starting event loop ')
        loop.run_forever()
    finally:
        loop.close()


if __name__ == '__main__':
    run_bot()
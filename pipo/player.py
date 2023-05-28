#!usr/bin/env python3
import re
import time
import random
import urllib
import logging
import threading
import multiprocessing.pool
from typing import List, Union, Optional
from functools import lru_cache

from yt_dlp import YoutubeDL

from pipo.config import settings
from pipo.music_queue.music_queue import MusicQueue
from pipo.music_queue.local_music_queue import LocalMusicQueue


class Player:

    __bot: None
    __logger: logging.Logger
    __url_fetch_pool: multiprocessing.pool.ThreadPool
    __player_thread: threading.Thread
    _music_queue: MusicQueue
    can_play: threading.Event

    def __init__(self, bot) -> None:
        self.__logger = logging.getLogger(__name__)
        self.__player_thread = None
        self.can_play = threading.Event()
        self.__bot = bot
        self._music_queue = LocalMusicQueue()  # TODO make more general
        self.__url_fetch_pool = multiprocessing.pool.ThreadPool(
            processes=settings.player.url_fetch.pool_size
        )

    def stop(self) -> None:
        self.__clear_queue()
        self.can_play.set()  # loop in __play_music_queue breaks due to empty queue
        self.__player_thread.join()
        self.__bot._voice_client.stop()

    def pause(self) -> None:
        self.__bot._voice_client.pause()

    def resume(self) -> None:
        self.__bot._voice_client.resume()

    async def leave(self) -> None:
        await self.__bot._voice_client.disconnect()

    def queue_size(self) -> int:
        return self._music_queue.size()

    def shuffle(self) -> None:
        self._music_queue.shuffle()

    def play(self, queries: Union[str, List[str]], shuffle: bool = False) -> List[str]:
        """_summary_

        _extended_summary_

        Parameters
        ----------
        queries : Union[str, List[str]]
            _description_
        shuffle : bool, optional
            _description_, by default False

        Returns
        -------
        List[str]
            Music urls added to the queue.
        """
        if (not self.__player_thread) or (
            self.__player_thread and not self.__player_thread.is_alive
        ):
            self._start_music_queue()
        if not isinstance(queries, (list, tuple)):  # ensure an Iterable is used
            queries = [
                queries,
            ]
        return self.__add_music(queries, shuffle)

    def __add_music(self, queries: List[str], shuffle: bool) -> List[str]:
        results = []
        for query in queries:
            if "/playlist?list=" in query:  # check if playlist
                with YoutubeDL({"extract_flat": True}) as ydl:
                    query = ydl.extract_info(url=query, download=False).get(
                        "queries",
                        [
                            query,
                        ],
                    )
            else:
                query = [
                    query,
                ]
            shuffle and random.shuffle(query)
            results = [
                result
                for result in self.__url_fetch_pool.map(
                    Player.get_youtube_audio,
                    queries,
                )
                if result
            ]
        if results:
            self._music_queue.add(results)
        return results

    def __clear_queue(self) -> None:
        self._music_queue.clear()

    def _start_music_queue(self) -> None:
        if self.__player_thread and not self.__player_thread.is_alive:
            self.__player_thread.join()
        self.__player_thread = threading.Thread(
            target=self.__play_music_queue, daemon=True
        )
        self.__player_thread.start()
        self.can_play.set()

    def __play_music_queue(self) -> None:
        while self.can_play.wait() and self.queue_size():
            self.can_play.clear()
            url = self._music_queue.get()
            if url:
                try:
                    self.__bot.submit_music(url)
                except Exception as exc:
                    self.__logger.warning(
                        "Unable to play next music. Error: %s", str(exc)
                    )
                    self.__bot.send_message(settings.player.messages.play_error)
        self.can_play.clear()
        self.__bot.become_idle()

    @staticmethod
    def get_youtube_url_from_query(query: str) -> Optional[str]:
        url = None
        if query:
            query = query.replace(" ", "+").encode("ascii", "ignore").decode()
            with urllib.request.urlopen(
                f"https://www.youtube.com/results?search_query={query}"
            ) as response:
                video_ids = re.findall(r"watch\?v=(\S{11})", response.read().decode())
                url = f"https://www.youtube.com/watch?v={video_ids[0]}"
        return url

    @staticmethod
    @lru_cache(maxsize=settings.player.url_fetch.max_cache_size)
    def get_youtube_audio(query: str) -> Optional[str]:
        """Obtains a youtube audio url.

        Given a query or a youtube url obtains the best quality audio url available.
        Retries fetching audio url in case of error, waiting a random period of
        time between each attempt.

        Parameters
        ----------
        query : str
            Youtube video url or query.

        Returns
        -------
        str
            Youtube audio url or None if no audio url was found.
        """
        if not (query.startswith("http") or query.startswith("https")):
            query = Player.get_youtube_url_from_query(query)
        logging.getLogger(__name__).info(
            "Trying to obtain youtube audio url for query: %s", query
        )
        url = None
        if query:
            for attempt in range(settings.player.url_fetch.retries):
                logging.getLogger(__name__).debug(
                    "Attempt %s to obtain youtube audio url for query: %s",
                    attempt,
                    query,
                )
                try:
                    with YoutubeDL({"format": "bestaudio/best"}) as ydl:
                        url = ydl.extract_info(url=query, download=False).get(
                            "url", None
                        )
                except:
                    logging.getLogger(__name__).warning(
                        "Unable to obtain audio url for query: %s", query
                    )
                if url:
                    logging.getLogger(__name__).info("Obtained audio url: %s", url)
                    return url
                time.sleep(settings.player.url_fetch.wait * random.random())
        logging.getLogger(__name__).info(
            "Unable to obtain audio url for query: %s", query
        )
        return None

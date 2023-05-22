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


class Player:

    __bot: None
    __logger: logging.Logger
    __lock: threading.Lock
    __url_fetch_pool: multiprocessing.pool.ThreadPool
    __player_thread: threading.Thread
    __music_queue: List[str]
    can_play: threading.Event

    def __init__(self, bot) -> None:
        self.__player_thread = None
        self.__logger = logging.getLogger(__name__)
        self.__bot = bot
        self.__music_queue = []
        self.__lock = threading.Lock()
        self.can_play = threading.Event()
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
        # used to solve method correctness issues without locks
        if self.__music_queue:
            sizes = [
                len(self.__music_queue)
                for _ in range(settings.player.queue.size_check_iterations)
            ]
            return round(sum(sizes) / len(sizes))
        return 0

    def shuffle(self) -> None:
        with self.__lock:
            random.shuffle(self.__music_queue)

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
            if ("/playlist?list=") in query:  # check if playlist
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
            with self.__lock:
                self.__music_queue.extend(results)
        return results

    def __clear_queue(self) -> None:
        with self.__lock:
            self.__music_queue = []

    def _start_music_queue(self) -> None:
        if self.__player_thread and not self.__player_thread.is_alive:
            self.__player_thread.join()
        self.__player_thread = threading.Thread(
            target=self.__play_music_queue, daemon=True
        )
        self.__player_thread.start()
        self.can_play.set()

    def _get_music_queue(self) -> List[str]:
        return self.__music_queue

    def __play_music_queue(self) -> None:
        while self.can_play.wait() and self.queue_size():
            self.can_play.clear()
            url = None
            try:
                with self.__lock:
                    url = self.__music_queue.pop()
            except IndexError as exc:
                self.__logger.warning("Music queue may be empty. Error: %s", str(exc))
            if url:
                try:
                    self.__bot.submit_music(url)
                except Exception as exc:
                    self.__logger.warning(
                        "Unable to play next music. Error: %s", str(exc)
                    )
                    self.__bot.send_message("Unable to play next music. Skipping...")
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
                try:  # required since library is really finicky
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

"""Deterministic TMDB artwork lookup with an intentionally small cache contract."""
from __future__ import annotations

import json
import math
import os
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Poster:
    tmdb_id: int | None
    poster_path: str | None
    looked_up_at: datetime


@dataclass(frozen=True)
class TitleSearchResult:
    """A user-selectable, canonical TMDB title.

    ``tmdb_id`` is intentionally local metadata.  It is never used as a Qloo
    entity identifier.
    """

    tmdb_id: int
    media_type: str
    title: str
    release_date: str | None
    poster_path: str | None


class TmdbUnavailable(Exception):
    """Autocomplete could not safely obtain results from TMDB."""


class TmdbClient:
    def __init__(
        self,
        api_key: str | None = None,
        opener=urlopen,
        image_opener=None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("TMDB_API_KEY", "")
        self.opener = opener
        # Keeping this injectable makes the CDN audit deterministic in tests
        # without changing the TMDB API transport boundary.
        self.image_opener = image_opener or opener

    def find_movie(
        self, title: str, release_year: int | None, runtime_minutes: int | None = None
    ) -> Poster:
        now = datetime.now(timezone.utc)
        if (
            not self.api_key
            or not isinstance(title, str)
            or not title.strip()
            or (
                release_year is not None
                and (isinstance(release_year, bool) or not isinstance(release_year, int))
            )
            or (
                runtime_minutes is not None
                and (isinstance(runtime_minutes, bool) or not isinstance(runtime_minutes, int))
            )
        ):
            return Poster(None, None, now)
        # Do not send a ``year`` filter here.  The artwork policy permits one
        # adjacent release year, and TMDB's filter would hide that otherwise
        # valid candidate before we can verify its title and distance locally.
        query = {"query": title, "api_key": self.api_key, "include_adult": "false"}
        request = Request("https://api.themoviedb.org/3/search/movie?" + urlencode(query), headers={"Accept": "application/json"})
        try:
            with self.opener(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            return Poster(None, None, now)
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            return Poster(None, None, now)
        matches: list[tuple[int, str | None, int, float]] = []
        seen_ids: set[int] = set()
        for item in results:
            tmdb_id = item.get("id") if isinstance(item, dict) else None
            if (
                not isinstance(item, dict)
                or not isinstance(tmdb_id, int)
                or isinstance(tmdb_id, bool)
                or tmdb_id < 1
            ):
                continue
            # The movie endpoint should already exclude television results,
            # but reject a contradictory provider payload defensively.
            media_type = item.get("media_type")
            if media_type is not None and media_type != "movie":
                continue
            # A contradictory movie-shaped response must not smuggle a TV
            # record into the artwork cache when the provider payload is
            # malformed and omits ``media_type``.
            if item.get("name") is not None or item.get("first_air_date") is not None:
                continue
            candidate_titles = (item.get("title"), item.get("original_title"))
            if not any(
                isinstance(candidate_title, str)
                and self._matches_title(title, candidate_title)
                for candidate_title in candidate_titles
            ):
                continue
            candidate_year = self._release_year(item.get("release_date"))
            # Artwork is only eligible when TMDB supplies a concrete release
            # year.  An exact normalized title may use an unambiguous result
            # one year either side of the provider year; unknown years are
            # never evidence for a persisted poster.
            if candidate_year is None:
                continue
            distance = 0
            if release_year is not None:
                distance = abs(int(candidate_year) - release_year)
                if distance > 1:
                    continue
            initial_path = self._poster_path(item.get("poster_path"))
            popularity = item.get("popularity")
            if (
                isinstance(popularity, bool)
                or not isinstance(popularity, (int, float))
                or not math.isfinite(float(popularity))
            ):
                popularity = 0.0
            if tmdb_id in seen_ids:
                continue
            seen_ids.add(tmdb_id)
            matches.append((tmdb_id, initial_path, distance, float(popularity)))

        # Prefer the nearest year.  A remaining tie may be resolved using
        # runtime evidence; otherwise use TMDB's own popularity ordering and
        # a stable ID fallback so an exact-title match receives artwork.
        nearest_distance = min((match[2] for match in matches), default=None)
        nearest = [match for match in matches if match[2] == nearest_distance]
        if not nearest:
            return Poster(None, None, now)
        if len(nearest) != 1:
            runtime_match = self._runtime_matched_movie(nearest, runtime_minutes)
            nearest = [runtime_match] if runtime_match is not None else [
                min(nearest, key=lambda match: (-match[3], match[0]))
            ]

        tmdb_id, initial_path, _, _ = nearest[0]
        return Poster(
            tmdb_id,
            self._audited_poster_path(tmdb_id=tmdb_id, initial_path=initial_path),
            now,
        )

    def _runtime_matched_movie(
        self,
        matches: list[tuple[int, str | None, int, float]],
        runtime_minutes: int | None,
    ) -> tuple[int, str | None, int, float] | None:
        """Break an otherwise unsafe title/year tie using verified runtime.

        Runtime is provider evidence, not a fuzzy preference: TMDB must have
        a uniquely closest detail runtime within five minutes, among the
        already verified title/year candidates.
        """
        if runtime_minutes is None or runtime_minutes < 1:
            return None
        runtime_matches: list[tuple[tuple[int, str | None, int, float], int]] = []
        for match in matches:
            tmdb_id = match[0]
            request = Request(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}?"
                + urlencode({"api_key": self.api_key}),
                headers={"Accept": "application/json"},
            )
            try:
                with self.opener(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("id") == tmdb_id
                and isinstance(payload.get("runtime"), int)
                and abs(payload["runtime"] - runtime_minutes) <= 5
            ):
                runtime_matches.append((match, abs(payload["runtime"] - runtime_minutes)))
        if not runtime_matches:
            return None
        closest_distance = min(distance for _, distance in runtime_matches)
        closest = [match for match, distance in runtime_matches if distance == closest_distance]
        return closest[0] if len(closest) == 1 else None

    def _audited_poster_path(
        self, *, tmdb_id: int, initial_path: str | None
    ) -> str | None:
        """Keep a working poster or find a replacement for the same movie.

        Search results sometimes contain a stale/missing CDN path or omit a
        poster because TMDB applied its default language filter.  The fallback
        is deliberately ID-scoped: it cannot turn an unavailable movie poster
        into artwork for another movie or a television result.
        """
        if initial_path and self._poster_url_is_available(initial_path):
            return initial_path

        excluded_paths = {initial_path} if initial_path else set()
        for include_image_language in (True, False):
            payload = self._request_images(tmdb_id, include_image_language)
            if payload is None:
                continue
            if payload.get("id") != tmdb_id:
                # Do not trust an images response unless it explicitly
                # confirms the canonical movie identity selected by
                # /search/movie.  A missing id is not proof of a same-movie
                # response and must not authorize a poster substitution.
                continue
            posters = payload.get("posters")
            if not isinstance(posters, list):
                continue
            for item in self._ordered_poster_items(
                posters, allow_non_preferred_language=not include_image_language
            ):
                path = self._poster_path(item.get("file_path"))
                if path is None or path in excluded_paths:
                    continue
                if self._poster_url_is_available(path):
                    return path
        return None

    def _request_images(self, tmdb_id: int, include_image_language: bool) -> dict | None:
        query = {"api_key": self.api_key}
        if include_image_language:
            # English and language-neutral posters are the polished default;
            # the second request below is the deliberate unfiltered fallback.
            query["include_image_language"] = "en,null"
        request = Request(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}/images?"
            + urlencode(query),
            headers={"Accept": "application/json"},
        )
        try:
            with self.opener(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _ordered_poster_items(
        posters: list[object], *, allow_non_preferred_language: bool = True
    ) -> tuple[dict, ...]:
        valid: list[tuple[int, int, dict]] = []
        for index, item in enumerate(posters):
            if not isinstance(item, dict):
                continue
            language = item.get("iso_639_1")
            if language is not None and not isinstance(language, str):
                continue
            preferred_language = language is None or language in {"null", "en"}
            if not allow_non_preferred_language and not preferred_language:
                continue
            # Preserve TMDB's order within each language tier so the fallback
            # remains deterministic and does not affect recommendation ranks.
            priority = 0 if preferred_language else 1
            valid.append((priority, index, item))
        valid.sort(key=lambda value: (value[0], value[1]))
        return tuple(item for _, _, item in valid)

    def _poster_url_is_available(self, path: str) -> bool:
        url = poster_url(path)
        if url is None:
            return False
        request = Request(url, method="HEAD", headers={"Accept": "image/*"})
        try:
            with self.image_opener(request, timeout=5) as response:
                return self._usable_image_response(response)
        except HTTPError as error:
            # Some CDNs do not implement HEAD.  A bounded GET is still an
            # availability check; an HTTP error remains a hard failure.
            if error.code not in {405, 501}:
                return False
            try:
                with self.image_opener(
                    Request(url, headers={"Accept": "image/*"}), timeout=5
                ) as response:
                    return self._usable_image_response(response)
            except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                return False
        except (URLError, TimeoutError, ValueError, OSError):
            return False

    @staticmethod
    def _usable_image_response(response: object) -> bool:
        status = getattr(response, "status", None)
        if status is None:
            status = getattr(response, "code", None)
        if isinstance(status, int) and not 200 <= status < 400:
            return False
        headers = getattr(response, "headers", None)
        content_type = None
        if headers is not None:
            try:
                content_type = headers.get("Content-Type") or headers.get("content-type")
            except AttributeError:
                content_type = None
        if content_type is None:
            return True
        if not isinstance(content_type, str):
            return False
        return content_type.casefold().split(";", 1)[0].startswith("image/")

    @staticmethod
    def _poster_path(path: object) -> str | None:
        return path if isinstance(path, str) and path.startswith("/") else None

    @staticmethod
    def _release_year(value: object) -> str | None:
        if not isinstance(value, str) or len(value) < 4:
            return None
        year = value[:4]
        return year if year.isdigit() else None

    def search_titles(self, query_text: str) -> tuple[TitleSearchResult, ...]:
        """Search movies and television without exposing the TMDB credential.

        The caller must still make the explicit selection; this method merely
        supplies possible matches.  A small verified alias map changes the
        remote query for common abbreviations, never the submitted selection.
        """
        if not self.api_key:
            raise TmdbUnavailable("TMDB is not configured")
        query_text = unicodedata.normalize("NFC", query_text).strip()
        if not query_text:
            return ()
        alias_query = {"aot": "Attack on Titan"}.get(query_text.casefold(), query_text)
        request = Request(
            "https://api.themoviedb.org/3/search/multi?"
            + urlencode({"query": alias_query, "api_key": self.api_key, "include_adult": "false"}),
            headers={"Accept": "application/json"},
        )
        try:
            with self.opener(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            raise TmdbUnavailable("TMDB search is unavailable") from error
        results = payload.get("results", []) if isinstance(payload, dict) else []
        selected: list[TitleSearchResult] = []
        seen: set[tuple[str, int]] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            media_type = item.get("media_type")
            tmdb_id = item.get("id")
            title = item.get("title") if media_type == "movie" else item.get("name")
            if media_type not in {"movie", "tv"} or not isinstance(tmdb_id, int) or not isinstance(title, str):
                continue
            title = unicodedata.normalize("NFC", title).strip()
            if not title or (media_type, tmdb_id) in seen:
                continue
            seen.add((media_type, tmdb_id))
            release_date = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
            selected.append(
                TitleSearchResult(
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    title=title,
                    release_date=release_date if isinstance(release_date, str) and release_date else None,
                    poster_path=item.get("poster_path") if isinstance(item.get("poster_path"), str) and item["poster_path"].startswith("/") else None,
                )
            )
            if len(selected) == 8:
                break
        return tuple(selected)

    def selected_title(
        self, *, tmdb_id: int, media_type: str
    ) -> TitleSearchResult | None:
        """Fetch a selected record by its provider-local id for submission.

        Registration deliberately ignores browser-supplied title/date/poster
        values.  This prevents a client from claiming a different work under a
        real id, while retaining a small, explicit provider boundary.
        """
        if not self.api_key:
            raise TmdbUnavailable("TMDB is not configured")
        if media_type not in {"movie", "tv"} or tmdb_id < 1:
            return None
        request = Request(
            f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?"
            + urlencode({"api_key": self.api_key}),
            headers={"Accept": "application/json"},
        )
        try:
            with self.opener(request, timeout=5) as response:
                item = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise TmdbUnavailable("TMDB title lookup is unavailable") from error
        except (URLError, TimeoutError, ValueError, OSError) as error:
            raise TmdbUnavailable("TMDB title lookup is unavailable") from error
        if not isinstance(item, dict) or item.get("id") != tmdb_id:
            return None
        title = item.get("title") if media_type == "movie" else item.get("name")
        if not isinstance(title, str) or not title.strip():
            return None
        release_date = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
        poster_path = item.get("poster_path")
        return TitleSearchResult(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=unicodedata.normalize("NFC", title).strip(),
            release_date=release_date if isinstance(release_date, str) and release_date else None,
            poster_path=poster_path if isinstance(poster_path, str) and poster_path.startswith("/") else None,
        )

    @staticmethod
    def _matches_title(submitted_title: str, provider_title: str) -> bool:
        submitted = TmdbClient._normalize_title(submitted_title)
        candidate = TmdbClient._normalize_title(provider_title)
        return submitted == candidate

    @staticmethod
    def _normalize_title(value: str) -> str:
        """Normalize only presentation differences, never title meaning."""
        # Collapsing whitespace makes persisted titles and provider titles
        # compare consistently while retaining punctuation, subtitles, and
        # other meaningful title distinctions.
        return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def poster_url(path: str | None) -> str | None:
    return (
        f"https://image.tmdb.org/t/p/w342{path}"
        if isinstance(path, str) and path.startswith("/")
        else None
    )


__all__ = ["Poster", "TitleSearchResult", "TmdbClient", "TmdbUnavailable", "poster_url"]

from __future__ import annotations


def build_website_sources(
    config: dict,
    *,
    core_display_names: dict[str, str],
    **_kwargs,
) -> list[dict]:
    websites = config.get("data_sources", {}).get("websites", {})
    parser_config = config.get("crawl_config", {}).get("parser", {})
    sources = []

    for source in websites.get("core", []):
        source_id = source.get("id")
        if not source_id or not source.get("url"):
            continue
        parser_name = source.get("parser_type", "zju_list")
        parser_meta = parser_config.get(parser_name, {})
        selectors = source.get("selectors", {})
        sources.append(
            {
                "id": source_id,
                "name": core_display_names.get(source_id, source.get("name") or source_id),
                "url": source["url"],
                "source_type": "core",
                "source_channel": "website",
                "category": "core",
                "parser_type": parser_name,
                "selectors": {
                    "list": selectors.get("list") or parser_meta.get("list_selector"),
                    "title": selectors.get("title") or parser_meta.get("title_selector"),
                    "date": selectors.get("date") or parser_meta.get("date_selector"),
                },
            }
        )

    for source in websites.get("colleges", []):
        lecture_url = source.get("lecture_url")
        source_id = source.get("id")
        if not source_id or not lecture_url:
            continue
        parser_name = source.get("parser_type", "zju_list")
        parser_meta = parser_config.get(parser_name, {})
        sources.append(
            {
                "id": source_id,
                "name": source.get("name") or source_id,
                "url": lecture_url,
                "source_type": "college",
                "source_channel": "website",
                "category": source.get("category") or "学院",
                "parser_type": parser_name,
                "selectors": {
                    "list": parser_meta.get("list_selector"),
                    "title": parser_meta.get("title_selector"),
                    "date": parser_meta.get("date_selector"),
                },
            }
        )

    return sources


def build_wechat_sources(
    config: dict,
    *,
    core_display_names: dict[str, str],
    wechat_core_source_map: dict[str, str],
    **_kwargs,
) -> list[dict]:
    websites = config.get("data_sources", {}).get("websites", {})
    wechat_accounts = config.get("data_sources", {}).get("wechat_accounts", {})

    college_meta = {
        source.get("id"): source
        for source in websites.get("colleges", [])
        if source.get("id")
    }

    sources = []

    for account in wechat_accounts.get("core", []):
        account_name = account.get("name")
        mapped_id = wechat_core_source_map.get(account.get("type"))
        if not account_name or not mapped_id:
            continue

        source_name = core_display_names.get(mapped_id, account_name)
        sources.append(
            {
                "id": mapped_id,
                "cache_key": f"wechat:{mapped_id}",
                "name": source_name,
                "url": None,
                "source_type": "core",
                "source_channel": "wechat",
                "category": "core",
                "mp_name": account_name,
                "priority": account.get("priority", 99),
            }
        )

    for account in wechat_accounts.get("colleges", []):
        college_id = account.get("college_id")
        account_name = account.get("name")
        if not college_id or not account_name:
            continue

        college = college_meta.get(college_id, {})
        sources.append(
            {
                "id": college_id,
                "cache_key": f"wechat:{college_id}",
                "name": college.get("name") or account_name,
                "url": college.get("url"),
                "source_type": "college",
                "source_channel": "wechat",
                "category": college.get("category") or "学院",
                "mp_name": account_name,
                "priority": account.get("priority", 99),
            }
        )

    return sources


class SourceChannelRegistry:
    def __init__(
        self,
        *,
        core_display_names: dict[str, str],
        wechat_core_source_map: dict[str, str],
    ):
        self._core_display_names = core_display_names
        self._wechat_core_source_map = wechat_core_source_map
        self._channels: dict[str, dict] = {}

    def register(
        self,
        channel: str,
        *,
        builder,
        adapter,
        service_method_name: str,
        source_builder_method_name: str,
    ) -> None:
        self._channels[channel] = {
            "builder": builder,
            "adapter": adapter,
            "service_method_name": service_method_name,
            "source_builder_method_name": source_builder_method_name,
        }

    def build_channel_sources(self, channel: str, config: dict) -> list[dict]:
        channel_meta = self._channels[channel]
        return channel_meta["builder"](
            config,
            core_display_names=self._core_display_names,
            wechat_core_source_map=self._wechat_core_source_map,
        )

    def build_sources(self, config: dict) -> list[dict]:
        sources = []
        for channel in self._channels:
            sources.extend(self.build_channel_sources(channel, config))
        return sources

    def build_merged_sources(self, config: dict) -> list[dict]:
        merged = {}
        for source in self.build_sources(config):
            existing = merged.get(source["id"])
            if existing:
                existing["source_channels"] = sorted(
                    set(existing.get("source_channels", []) + [source["source_channel"]])
                )
                continue

            merged[source["id"]] = dict(source)
            merged[source["id"]]["source_channels"] = [source["source_channel"]]
        return list(merged.values())

    def get_adapter(self, channel: str):
        return self._channels[channel]["adapter"]

    def iter_channels(self) -> list[str]:
        return list(self._channels.keys())

    def get_service_fetcher(self, service, channel: str):
        method_name = self._channels[channel]["service_method_name"]
        return getattr(service, method_name)

    def get_service_source_builder(self, service, channel: str):
        method_name = self._channels[channel]["source_builder_method_name"]
        return getattr(service, method_name)

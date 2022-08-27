import asyncio
import datetime
from functools import cached_property
from itertools import chain
from typing import Union

import altair as alt
import httpx
import pandas as pd


class onePA:
    FACILITIES = (
        "BADMINTON COURTS",
        "BASKETBALL COURT",
        "BBQ PIT (CC)",
        "BBQ PIT (RC)",
        "FUTSAL COURT",
        "SOCCER FIELD",
        "SQUASH COURT",
        "STUDY & WORKSPACES",
        "TABLE TENNIS ROOM",
        "TENNIS COURT",
    )

    BASE_URL = "https://www.onepa.gov.sg/pacesapi"
    FACILITY_SEARCH_ENDPOINT = "/facilitysearch/searchjson"
    FACILITY_SLOTS_ENDPOINT = "/facilityavailability/GetFacilitySlots"

    def __init__(self, facility: str):
        assert facility in self.FACILITIES
        self.facility = facility

    @cached_property
    def outlet_names(self):
        outlet_names = []
        page_num = 1
        while True:
            params = {"facility": self.facility, "page": page_num}
            r = httpx.get(self.BASE_URL + self.FACILITY_SEARCH_ENDPOINT, params=params)

            results = r.json()["data"]["results"]

            page_outlet_names = [result["outlet"] for result in results]
            outlet_names.extend(page_outlet_names)

            page_num += 1
            if len(page_outlet_names) < 10:
                break
        outlet_names = sorted(outlet_names)
        return outlet_names

    async def _batch_available_outlets(self, client, batch_outlets, date):
        date_str = date.strftime("%d/%m/%Y")
        params = {
            "outlet": batch_outlets,
            "facility": self.facility,
            "date": date_str,
            "time": "all",
        }
        r = await client.get(
            self.BASE_URL + self.FACILITY_SEARCH_ENDPOINT, params=params
        )
        results = r.json()["data"]["results"]
        results = [dict(data, **{"date": date}) for data in results]
        return results

    async def available_outlets(self, dates: Union[datetime.date, list[datetime.date]]):
        if isinstance(dates, datetime.date):
            dates = [dates]

        PAGE_SIZE = 10
        async with httpx.AsyncClient(timeout=60 * 2) as client:
            tasks = []
            for date in dates:
                outlet_names = self.outlet_names

                for i in range(0, len(outlet_names), PAGE_SIZE):
                    batch_outlets = ",".join(
                        outlet_names[i : i + PAGE_SIZE]
                    )  # batch of 10 outlets
                    result = self._batch_available_outlets(client, batch_outlets, date)
                    tasks.append(asyncio.ensure_future(result))
            outlet_availability_nested = await asyncio.gather(*tasks)
        return list(chain.from_iterable(outlet_availability_nested))

    async def available_outlets_df(
        self, dates: Union[datetime.date, list[datetime.date]]
    ):
        outlet_availability = await self.available_outlets(dates)
        expanded_df = pd.json_normalize(outlet_availability)
        if "outlet" not in expanded_df.columns:
            outlet_df = pd.DataFrame(
                columns=["outlet", "count", "bookingUrl", "publicPrice", "membersPrice"]
            )
            return outlet_df
        outlet_df = (
            expanded_df[
                [
                    "outlet",
                    "count",
                    "productUrl",
                    "price.publicPrice",
                    "price.membersPrice",
                    "date",
                ]
            ]
            .assign(
                productUrl=lambda row: "https://www.onepa.gov.sg" + row["productUrl"]
            )
            .rename(
                columns={
                    "productUrl": "bookingUrl",
                    "price.publicPrice": "publicPrice",
                    "price.membersPrice": "membersPrice",
                }
            )
        )
        outlet_df["date"] = pd.to_datetime(outlet_df["date"])
        return outlet_df

    async def _batch_available_times_per_outlet(self, client, outlet, date):

        date_str = date.strftime("%d/%m/%Y")
        selected_facility = (
            f"{outlet.replace(' ' , '')}_{self.facility.replace(' ', '')}"
        )

        date_slot_info = []
        params = {"selectedFacility": selected_facility, "selectedDate": date_str}

        r = await client.get(
            self.BASE_URL + self.FACILITY_SLOTS_ENDPOINT,
            params=params,
            timeout=60,
        )
        resource_statuses = r.json()["response"]["resourceList"]

        if resource_statuses is not None:
            for resource_status in resource_statuses:
                slot_info_list = resource_status["slotList"]
                # Add link to page

                date_slot_info.extend(slot_info_list)

            date_slot_info = [
                dict(
                    slot_info,
                    **{
                        "bookingUrl": "https://www.onepa.gov.sg/facilities/availability?facilityId="
                        + selected_facility
                    },
                )
                for slot_info in date_slot_info
            ]
        return date_slot_info

    async def available_times_per_outlet(
        self, outlet, dates: Union[datetime.date, list[datetime.date]]
    ):
        async with httpx.AsyncClient(timeout=60 * 2) as client:
            tasks = []
            for date in dates:
                date_slot_info = self._batch_available_times_per_outlet(
                    client, outlet, date
                )
                tasks.append(asyncio.ensure_future(date_slot_info))
            date_slot_info_nested = await asyncio.gather(*tasks)
        return list(chain.from_iterable(date_slot_info_nested))

    async def available_times_per_outlet_df(
        self, outlet, dates: Union[datetime.date, list[datetime.date]]
    ):
        responses = await self.available_times_per_outlet(outlet, dates)

        df = (
            pd.DataFrame(responses)
            .groupby(
                [
                    "timeRangeId",
                    "timeRangeName",
                    "startTime",
                    "endTime",
                    "isPeak",
                    "bookingUrl",
                ]
            )[["isAvailable"]]
            .sum()
            .reset_index()
        )
        return df


def availability_plot_times(df):
    base_chart = alt.Chart(df).encode(
        x=alt.X(
            "date(startTime):O",
            title="Day of Month",
            sort=alt.EncodingSortField(field="startTime", order="ascending"),
        ),
        y=alt.Y("hoursminutes(startTime):O", title="Start Time"),
        tooltip=[
            "timeRangeName",
            "isPeak",
            "isAvailable",
            alt.Tooltip("day(startTime)", title="day"),
            alt.Tooltip("startTime:T", title="date"),
        ],
        href="bookingUrl:N",
    )

    available_slots = base_chart.transform_filter(alt.datum.isAvailable > 0).encode(
        color=alt.Color(
            "isAvailable:O",
            scale=alt.Scale(
                scheme="yellowgreen"
            ),  # https://vega.github.io/vega/docs/schemes/
            legend=alt.Legend(title="Available slots"),
        )
    )

    chart = available_slots.mark_rect() + base_chart.mark_rect(opacity=0)

    chart["usermeta"] = {"embedOptions": {"loader": {"target": "_blank"}}}
    return chart.properties(title="No. of available slots by time, date")


def availability_plot_dates(df):
    chart = (
        alt.Chart(df)
        .mark_rect()
        .encode(
            x=alt.X(
                "date(date):O",
                title="Day of Month",
                sort=alt.EncodingSortField(field="date", order="ascending"),
            ),
            y=alt.Y("outlet:N"),
            color=alt.Color(
                "count:O",
                scale=alt.Scale(
                    scheme="yellowgreen"
                ),  # https://vega.github.io/vega/docs/schemes/
                legend=alt.Legend(title="Available slots"),
            ),
            href="bookingUrl:N",
            tooltip=[
                "outlet",
                "count",
                "publicPrice",
                "membersPrice",
                alt.Tooltip("day(date)", title="day"),
                "date",
            ],
        )
    )
    chart["usermeta"] = {"embedOptions": {"loader": {"target": "_blank"}}}
    return chart.properties(title="No. of slots by location, date")

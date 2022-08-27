import asyncio
import datetime

import pandas as pd
import streamlit as st

from checkers import availability_plot_dates, availability_plot_times, onePA


def plot_all_outlets_free_count(facility_PA, dates):
    if st.button("Search available slot for all outlets"):
        with st.spinner("Fetching number of available slots, takes a minute..."):
            df = asyncio.run(facility_PA.available_outlets_df(dates))
        chart = availability_plot_dates(df)
        st.altair_chart(chart)
        st.info("Outlets/timings are omitted if none available")


def plot_outlet_free_timings(facility_PA, dates):
    outlet = st.selectbox("Outlet", facility_PA.outlet_names)
    if st.button("Search available times for outlet"):
        with st.spinner("Fetching available times for outlet, takes a minute..."):
            df = asyncio.run(facility_PA.available_times_per_outlet_df(outlet, dates))
        chart = availability_plot_times(df)
        st.altair_chart(chart)


onePA = st.experimental_singleton(onePA)

st.header("Quickly check onePA facility availability")

chosen_facility = st.selectbox("Facility Type", onePA.FACILITIES)
facility_PA = onePA(chosen_facility)

view_mapping = {
    "All outlets - Number of free slots": plot_all_outlets_free_count,
    "Single outlet - Timing of free slots": plot_outlet_free_timings,
}
view_type = st.selectbox("View Type", view_mapping.keys())

today = datetime.date.today()
next_week = today + datetime.timedelta(7)
max_available_date = today + datetime.timedelta(17)
date_range = st.date_input(
    "Dates to check",
    value=(today, next_week),
    min_value=today,
    max_value=max_available_date,
)

# min-max dates to list of all dates
try:
    dates = pd.date_range(*date_range).date

    if facility_PA.outlet_names:
        plotter = view_mapping[view_type]
        plotter(facility_PA, dates)
    else:
        st.warning("No outlets available")

except ValueError:
    st.error("Please select start and end date")
except KeyError:
    st.warning("No outlets/timings available")


# Reset when buggy
if st.button("Reset app"):
    st.experimental_singleton.clear()

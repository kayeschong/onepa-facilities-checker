import asyncio
import datetime

import pandas as pd
import streamlit as st

from checkers import onePA

st.header("Quickly check onePA facility availability")

chosen_facility = st.selectbox("Facility Type", onePA.FACILITIES)
facility_PA = onePA(chosen_facility)
available_outlets = (
    (["All"] + facility_PA.outlet_names) if len(facility_PA.outlet_names) else []
)

outlet = st.selectbox("Outlet", available_outlets)

today = datetime.date.today()
tomorrow = today + datetime.timedelta(1)
max_available_date = today + datetime.timedelta(17)
date_range = st.date_input(
    "Dates to check",
    value=(today, tomorrow),
    min_value=today,
    max_value=max_available_date,
)

dates = pd.date_range(*date_range).date

if outlet == "All":
    if st.button("Search available slot for all outlets"):
        with st.spinner("Fetching available slots, takes a minute..."):
            df = asyncio.run(facility_PA.available_outlets_df(dates))
        chart = onePA.availability_plot_dates(df)
        st.altair_chart(chart)
else:
    if st.button("Search available times for outlet"):
        with st.spinner("Fetching available times for outlet"):
            df = asyncio.run(facility_PA.available_times_per_outlet_df(outlet, dates))
        chart = onePA.availability_plot_times(df)
        st.altair_chart(chart)

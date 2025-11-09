#!/usr/bin/env python3
"""AWS Cost Dashboard - Interactive Streamlit App"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Pricing Constants
LAMBDA_COST_PER_GB_SEC = 0.0000133334
LAMBDA_COST_PER_REQUEST = 0.0000002
APIGW_COST_PER_REQUEST = 0.000001
LAMBDA_FREE_REQUESTS = 1_000_000
LAMBDA_FREE_GB_SECONDS = 400_000

RDS_INSTANCE_COST_PER_HOUR = 0.016
RDS_STORAGE_COST_PER_GB_MONTH = 0.115
RDS_STORAGE_GB = 20
RDS_MONTHLY_COST = (RDS_INSTANCE_COST_PER_HOUR * 730) + \
    (RDS_STORAGE_GB * RDS_STORAGE_COST_PER_GB_MONTH)

S3_STORAGE_COST_PER_GB_MONTH = 0.023
S3_PUT_COST_PER_1000 = 0.005
S3_GET_COST_PER_1000 = 0.0004
S3_FILE_SIZE_MB = 5

DATA_TRANSFER_OUT_COST_PER_GB = 0.09
DATA_TRANSFER_OUT_FREE_GB = 1.0
CROSS_AZ_COST_PER_GB = 0.01
AVG_RESPONSE_SIZE_BYTES = 538
AVG_DB_QUERY_KB = 2
AVG_DB_RESPONSE_KB = 3
CROSS_AZ_RATIO = 0.5

CLOUDWATCH_INGESTION_COST_PER_GB = 0.25
CLOUDWATCH_STORAGE_COST_PER_GB_MONTH = 0.03
LOG_RETENTION_DAYS = 7
AVG_LAMBDA_LOG_BYTES_PER_INVOCATION = 3389
AVG_APIGW_LOG_BYTES_PER_REQUEST = 273

MEMORY_MB = 512
DURATION_MS = 229


def calc_costs(company_users, active_users, sessions_per_day, days):
    # Invocations: I(N) = 36 + 4N
    invoc_per_session = 36 + (4 * company_users)
    total_invocations = int(
        invoc_per_session * active_users * sessions_per_day * days)

    # Lambda
    gb_seconds = total_invocations * (MEMORY_MB / 1024) * (DURATION_MS / 1000)
    lambda_compute = max(
        0, gb_seconds - LAMBDA_FREE_GB_SECONDS) * LAMBDA_COST_PER_GB_SEC
    lambda_requests = max(0, total_invocations -
                          LAMBDA_FREE_REQUESTS) * LAMBDA_COST_PER_REQUEST
    lambda_total = lambda_compute + lambda_requests

    # API Gateway
    apigw_total = total_invocations * APIGW_COST_PER_REQUEST

    # RDS
    rds_cost = (RDS_MONTHLY_COST / 30) * days

    # S3
    total_sessions = active_users * sessions_per_day * days
    s3_put_cost = total_sessions * (S3_PUT_COST_PER_1000 / 1000)
    s3_get_cost = total_sessions * (S3_GET_COST_PER_1000 / 1000)
    s3_storage_gb = (total_sessions * S3_FILE_SIZE_MB) / 1024
    s3_storage_cost = s3_storage_gb * \
        S3_STORAGE_COST_PER_GB_MONTH * (days / 30)
    s3_total = s3_put_cost + s3_get_cost + s3_storage_cost

    # Data Transfer
    apigw_out_gb = (total_invocations * AVG_RESPONSE_SIZE_BYTES) / (1024**3)
    apigw_out_billable_gb = max(
        0, apigw_out_gb - (DATA_TRANSFER_OUT_FREE_GB * (days / 30)))
    apigw_transfer_cost = apigw_out_billable_gb * DATA_TRANSFER_OUT_COST_PER_GB

    cross_az_invocations = total_invocations * CROSS_AZ_RATIO
    db_query_gb = (cross_az_invocations * AVG_DB_QUERY_KB) / (1024**2)
    db_response_gb = (cross_az_invocations * AVG_DB_RESPONSE_KB) / (1024**2)
    cross_az_cost = (db_query_gb + db_response_gb) * CROSS_AZ_COST_PER_GB

    data_transfer_total = apigw_transfer_cost + cross_az_cost

    # CloudWatch Logs
    lambda_log_bytes = total_invocations * AVG_LAMBDA_LOG_BYTES_PER_INVOCATION
    apigw_log_bytes = total_invocations * AVG_APIGW_LOG_BYTES_PER_REQUEST
    total_log_gb = (lambda_log_bytes + apigw_log_bytes) / (1024**3)
    cloudwatch_ingestion = total_log_gb * CLOUDWATCH_INGESTION_COST_PER_GB
    cloudwatch_storage = total_log_gb * \
        CLOUDWATCH_STORAGE_COST_PER_GB_MONTH * (LOG_RETENTION_DAYS / 30)
    cloudwatch_total = cloudwatch_ingestion + cloudwatch_storage

    # Total
    total = lambda_total + apigw_total + rds_cost + \
        s3_total + data_transfer_total + cloudwatch_total

    return {
        'invocations': total_invocations,
        'sessions': int(total_sessions),
        'lambda': lambda_total,
        'apigw': apigw_total,
        'rds': rds_cost,
        's3': s3_total,
        'data_transfer': data_transfer_total,
        'cloudwatch': cloudwatch_total,
        'total': total
    }


def main():
    st.set_page_config(page_title="AWS Cost Breakdown", layout="wide")

    st.title("AWS Cost Breakdown Dashboard")

    # Sidebar inputs
    st.sidebar.header("⚙️ Configuration")

    company_users = st.sidebar.number_input(
        "Company Users",
        min_value=1,
        max_value=1000,
        value=2,
        step=1,
        help="Number of users in the company (affects invocations per session)"
    )

    active_users = st.sidebar.number_input(
        "Active Users",
        min_value=1,
        max_value=1000,
        value=1,
        step=1,
        help="Number of users actively using the product"
    )

    sessions_per_day = st.sidebar.slider(
        "Sessions per User per Day",
        min_value=1,
        max_value=50,
        value=1,
        step=1,
        help="Average sessions per user per day"
    )

    days = st.sidebar.slider(
        "Number of Days",
        min_value=1,
        max_value=30,
        value=1,
        step=1,
        help="Time period for cost calculation"
    )

    # Calculate costs
    results = calc_costs(company_users, active_users, sessions_per_day, days)

    # Display key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Cost", f"${results['total']:.2f}")
    with col2:
        monthly_cost = (results['total'] / days) * 30
        st.metric("Monthly Projection", f"${monthly_cost:.2f}")
    with col3:
        st.metric("Total Invocations", f"{results['invocations']:,}")
    with col4:
        st.metric("Total Sessions", f"{results['sessions']:,}")

    # Cost breakdown
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Cost by Service")

        # Prepare data for bar chart
        services = ['Lambda', 'API Gateway', 'RDS',
                    'S3', 'Data Transfer', 'CloudWatch']
        costs = [
            results['lambda'],
            results['apigw'],
            results['rds'],
            results['s3'],
            results['data_transfer'],
            results['cloudwatch']
        ]

        # Create bar chart
        fig_bar = go.Figure(data=[
            go.Bar(
                x=services,
                y=costs,
                text=[f"${c:.2f}" for c in costs],
                textposition='auto',
                marker_color=['#FF6B6B', '#4ECDC4', '#45B7D1',
                              '#FFA07A', '#98D8C8', '#C7CEEA']
            )
        ])
        fig_bar.update_layout(
            yaxis_title="Cost ($)",
            height=400,
            showlegend=False
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        st.subheader("🥧 Cost Distribution")

        # Create pie chart (filter out $0 costs)
        filtered_services = []
        filtered_costs = []
        for service, cost in zip(services, costs):
            if cost > 0:
                filtered_services.append(service)
                filtered_costs.append(cost)

        fig_pie = go.Figure(data=[go.Pie(
            labels=filtered_services,
            values=filtered_costs,
            hole=0.3,
            marker_colors=['#FF6B6B', '#4ECDC4',
                           '#45B7D1', '#FFA07A', '#98D8C8', '#C7CEEA']
        )])
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(height=400)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Detailed breakdown table
    st.markdown("---")
    st.subheader("📋 Detailed Cost Breakdown")

    df = pd.DataFrame({
        'Service': services,
        'Cost': costs,
        'Percentage': [f"{(c/results['total']*100):.1f}%" if results['total'] > 0 else "0%" for c in costs]
    })
    df['Cost'] = df['Cost'].apply(lambda x: f"${x:.6f}")

    st.dataframe(df, use_container_width=True, hide_index=True)


if __name__ == '__main__':
    main()

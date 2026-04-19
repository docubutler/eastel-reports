from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    mysql_type: str
    nullable: bool = True
    primary_key: bool = False


@dataclass(frozen=True)
class TableSpec:
    table_name: str
    source_name: str
    columns: tuple[ColumnSpec, ...]
    indexes: tuple[tuple[str, ...], ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def primary_keys(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns if column.primary_key)


REQUEST_TABLE = TableSpec(
    table_name="request_logs",
    source_name=r"",
    #source_name="request-small.csv",
    columns=(
        ColumnSpec("request_log_id", "BIGINT", nullable=False, primary_key=True),
        ColumnSpec("currency_id", "INT", nullable=False),
        ColumnSpec("service_type_id", "INT", nullable=False),
        ColumnSpec("service_provider_id", "INT", nullable=False),
        ColumnSpec("rate_plan_id", "INT", nullable=False),
        ColumnSpec("account_id", "INT", nullable=False),
        ColumnSpec("sim_id", "BIGINT", nullable=False),
        ColumnSpec("sim_service_plan_id", "BIGINT", nullable=False),
        ColumnSpec("customer_id", "INT", nullable=False),
        ColumnSpec("user_id", "INT", nullable=False),
        ColumnSpec("cr_user", "INT", nullable=False),
        ColumnSpec("cr_time", "DATETIME(6)", nullable=False),
        ColumnSpec("up_user", "INT", nullable=False),
        ColumnSpec("up_time", "DATETIME(6)", nullable=False),
        ColumnSpec("record_status", "INT", nullable=False),
        ColumnSpec("display_order", "INT", nullable=False),
        ColumnSpec("req_type", "VARCHAR(10)", nullable=False),
        ColumnSpec("req_time", "DATETIME(6)", nullable=False),
        ColumnSpec("session_id", "VARCHAR(255)", nullable=False),
        ColumnSpec("session_req_num", "INT", nullable=False),
        ColumnSpec("iccid", "VARCHAR(32)", nullable=False),
        ColumnSpec("msisdn", "VARCHAR(32)", nullable=False),
        ColumnSpec("imei", "VARCHAR(32)"),
        ColumnSpec("imsi", "VARCHAR(32)", nullable=False),
        ColumnSpec("roaming_mccmnc", "VARCHAR(16)"),
        ColumnSpec("rat_type", "VARCHAR(16)"),
        ColumnSpec("init_granted_volume", "DECIMAL(30,16)"),
        ColumnSpec("update_used_volume", "DECIMAL(30,16)"),
        ColumnSpec("total_used_volume", "DECIMAL(30,16)"),
        ColumnSpec("exchange_rate", "DECIMAL(30,16)"),
        ColumnSpec("cost_currency_cd", "VARCHAR(8)"),
        ColumnSpec("cost_exchange_rate", "DECIMAL(30,16)"),
        ColumnSpec("price_currency_cd", "VARCHAR(8)"),
        ColumnSpec("price_exchange_rate", "DECIMAL(30,16)"),
        ColumnSpec("cost_init_granted_money", "DECIMAL(30,16)"),
        ColumnSpec("cost_update_used_money", "DECIMAL(30,16)"),
        ColumnSpec("cost_total_used_money", "DECIMAL(30,16)"),
        ColumnSpec("price_init_granted_money", "DECIMAL(30,16)"),
        ColumnSpec("price_update_used_money", "DECIMAL(30,16)"),
        ColumnSpec("price_total_used_money", "DECIMAL(30,16)"),
        ColumnSpec("validity_time", "INT"),
        ColumnSpec("rating_group", "VARCHAR(32)"),
        ColumnSpec("user_location_info", "VARCHAR(255)"),
        ColumnSpec("apn", "VARCHAR(100)"),
        ColumnSpec("service_context", "VARCHAR(255)"),
        ColumnSpec("charging_characteristic", "VARCHAR(64)"),
        ColumnSpec("sgsn_address", "VARCHAR(64)"),
        ColumnSpec("notes", "VARCHAR(255)"),
        ColumnSpec("addon_imsi", "VARCHAR(32)"),
        ColumnSpec("addon_msisdn", "VARCHAR(32)"),
        ColumnSpec("service_type_sub_cd", "VARCHAR(32)"),
        ColumnSpec("opposite_number", "VARCHAR(64)"),
        ColumnSpec("roaming_destination_id", "INT"),
        ColumnSpec("act_update_used_volume", "DECIMAL(30,16)"),
        ColumnSpec("act_total_used_volume", "DECIMAL(30,16)"),
        ColumnSpec("act_price_update_used_money", "DECIMAL(30,16)"),
        ColumnSpec("act_price_total_used_money", "DECIMAL(30,16)"),
        ColumnSpec("act_cost_update_used_money", "DECIMAL(30,16)"),
        ColumnSpec("act_cost_total_used_money", "DECIMAL(30,16)"),
        ColumnSpec("additional_sim_id", "BIGINT"),
        ColumnSpec("additional_roaming_destination_id", "INT"),
        ColumnSpec("operation_status", "VARCHAR(32)"),
    ),
    indexes=(
        ("sim_id",),
        ("customer_id",),
        ("account_id",),
        ("rate_plan_id",),
        ("msisdn",),
        ("imsi",),
        ("iccid",),
        ("req_time",),
        ("session_id",),
        ("roaming_destination_id",),
        ("customer_id", "req_time"),
        ("sim_id", "req_time"),
    ),
)


USAGE_TABLE = TableSpec(
    table_name="iot_portal_tb_usage_log_rep",
    #source_name=r"D:\DB_repos\eastel-reports\iot_portal_tb_usage_log_rep-lt-16-MAR-26\iot_portal_tb_usage_log_rep-lt-16-MAR-26.csv",
    #source_name=r"D:\DB_repos\eastel-reports\aakash-calling-shawn-eastel-logs.txt",
    #source_name=r"D:\DB_repos\eastel-reports\RG500018-payg-data\RG500018 payg data-1776162941679",
    source_name=r"D:\DB_repos\eastel-reports\face-time_ALL_9-APR_to_11-APR.csv",
    columns=(
        ColumnSpec("usage_log_id", "BIGINT", nullable=False, primary_key=True),
        ColumnSpec("rate_plan_id", "INT", nullable=False),
        ColumnSpec("currency_id", "INT", nullable=False),
        ColumnSpec("user_id", "INT", nullable=False),
        ColumnSpec("customer_id", "INT", nullable=False),
        ColumnSpec("sim_id", "BIGINT", nullable=False),
        ColumnSpec("service_type_id", "INT", nullable=False),
        ColumnSpec("service_provider_id", "INT", nullable=False),
        ColumnSpec("sim_service_plan_id", "BIGINT", nullable=False),
        ColumnSpec("account_id", "INT", nullable=False),
        ColumnSpec("cr_user", "INT", nullable=False),
        ColumnSpec("cr_time", "DATETIME(6)", nullable=False),
        ColumnSpec("up_user", "INT", nullable=False),
        ColumnSpec("up_time", "DATETIME(6)", nullable=False),
        ColumnSpec("record_status", "INT", nullable=False),
        ColumnSpec("last_session_req_num", "INT"),
        ColumnSpec("session_id", "VARCHAR(255)", nullable=False),
        ColumnSpec("iccid", "VARCHAR(32)", nullable=False),
        ColumnSpec("msisdn", "VARCHAR(32)", nullable=False),
        ColumnSpec("imei", "VARCHAR(32)"),
        ColumnSpec("imsi", "VARCHAR(32)", nullable=False),
        ColumnSpec("service_type_sub_cd", "VARCHAR(32)"),
        ColumnSpec("roaming_mccmnc", "VARCHAR(16)"),
        ColumnSpec("rat_type", "VARCHAR(16)"),
        ColumnSpec("usage_unit", "DECIMAL(30,16)"),
        ColumnSpec("usage_start_time", "DATETIME(6)"),
        ColumnSpec("usage_update_time", "DATETIME(6)"),
        ColumnSpec("usage_end_time", "DATETIME(6)"),
        ColumnSpec("cost_amount", "DECIMAL(30,16)"),
        ColumnSpec("price_amount", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_quota_unit", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_cost_per_unit", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_quota_cost", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_price_per_unit", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_quota_price", "DECIMAL(30,16)"),
        ColumnSpec("addon_imsi", "VARCHAR(32)"),
        ColumnSpec("addon_msisdn", "VARCHAR(32)"),
        ColumnSpec("last_grant_shared_bucket_type_ids", "VARCHAR(64)"),
        ColumnSpec("opposite_number", "VARCHAR(64)"),
        ColumnSpec("roaming_destination_id", "INT"),
        ColumnSpec("act_usage_unit", "DECIMAL(30,16)"),
        ColumnSpec("act_cost_amount", "DECIMAL(30,16)"),
        ColumnSpec("act_price_amount", "DECIMAL(30,16)"),
        ColumnSpec("last_grant_vt", "INT"),
        ColumnSpec("last_grant_sim_service_plan_id", "BIGINT"),
        ColumnSpec("last_grant_request_log_id", "BIGINT"),
        ColumnSpec("notes", "VARCHAR(255)"),
        ColumnSpec("additional_sim_id", "BIGINT"),
        ColumnSpec("additional_roaming_destination_id", "INT"),
        ColumnSpec("mt_sip_diverted", "TINYINT"),
        ColumnSpec("original_voice_call_type", "VARCHAR(64)"),
        ColumnSpec("actual_opposite_number", "VARCHAR(64)"),
        ColumnSpec("pdp_address", "VARCHAR(64)"),
        ColumnSpec("last_grant_sim_service_plan_bucket_id", "BIGINT"),
        ColumnSpec("last_grant_sim_service_plan_bucket_start_ref", "DATETIME(6)"),
        ColumnSpec("last_grant_sim_service_plan_detail_id", "BIGINT"),
        ColumnSpec("sim_master_id", "BIGINT"),
        ColumnSpec("rating_group", "VARCHAR(32)"),
        ColumnSpec("traffic_rat", "VARCHAR(16)"),
        ColumnSpec("last_grant_sim_service_plan_bucket_purchase_seq", "VARCHAR(32)"),
    ),
    indexes=(
        ("sim_id",),
        ("customer_id",),
        ("account_id",),
        ("rate_plan_id",),
        ("msisdn",),
        ("imsi",),
        ("iccid",),
        ("usage_start_time",),
        ("usage_end_time",),
        ("session_id",),
        ("last_grant_request_log_id",),
        ("roaming_destination_id",),
        ("customer_id", "usage_start_time"),
        ("sim_id", "usage_start_time"),
    ),
)


TABLE_SPECS = (REQUEST_TABLE, USAGE_TABLE)

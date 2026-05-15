CREATE TABLE IF NOT EXISTS public.iot_portal_tb_request_log
(
    request_log_id numeric(20,0) NOT NULL DEFAULT nextval('iot_portal_seq_request_log'),
    
    currency_id numeric(20,0) NOT NULL,
    service_type_id numeric(20,0) NOT NULL,
    service_provider_id numeric(20,0) NOT NULL,
    rate_plan_id numeric(20,0) NOT NULL,
    account_id numeric(20,0) NOT NULL,
    sim_id numeric(20,0) NOT NULL,
    sim_service_plan_id numeric(20,0) NOT NULL,

    customer_id numeric(20,0) NOT NULL DEFAULT 0,
    user_id numeric(20,0) NOT NULL DEFAULT 0,

    cr_user numeric(20,0) NOT NULL DEFAULT 0,
    cr_time timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,

    up_user numeric(20,0) NOT NULL DEFAULT 0,
    up_time timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,

    record_status numeric(2,0) NOT NULL DEFAULT 0,
    display_order numeric(4,0) NOT NULL DEFAULT 0,

    req_type varchar(50),
    req_time timestamp,

    session_id varchar(300),
    session_req_num numeric(20,0),

    iccid varchar(50),
    msisdn varchar(50),
    imei varchar(50),
    imsi varchar(50),

    roaming_mccmnc varchar(50),
    rat_type varchar(50),

    init_granted_volume numeric(32,16),
    update_used_volume numeric(32,16),
    total_used_volume numeric(32,16),

    exchange_rate numeric(32,16),

    cost_currency_cd varchar(50),
    cost_exchange_rate numeric(32,16),

    price_currency_cd varchar(50),
    price_exchange_rate numeric(32,16),

    cost_init_granted_money numeric(32,16),
    cost_update_used_money numeric(32,16),
    cost_total_used_money numeric(32,16),

    price_init_granted_money numeric(32,16),
    price_update_used_money numeric(32,16),
    price_total_used_money numeric(32,16),

    validity_time numeric(8,0),

    rating_group varchar(50),
    user_location_info varchar(50),
    apn varchar(50),
    service_context varchar(50),
    charging_characteristic varchar(50),
    sgsn_address varchar(50),

    notes varchar(300),

    addon_imsi varchar(50),
    addon_msisdn varchar(50),

    service_type_sub_cd varchar(50),
    opposite_number varchar(50),

    roaming_destination_id numeric(20,0) NOT NULL DEFAULT 0,

    act_update_used_volume numeric(32,16) NOT NULL DEFAULT 0,
    act_total_used_volume numeric(32,16) NOT NULL DEFAULT 0,

    act_price_update_used_money numeric(32,16) NOT NULL DEFAULT 0,
    act_price_total_used_money numeric(32,16) NOT NULL DEFAULT 0,

    act_cost_update_used_money numeric(32,16) NOT NULL DEFAULT 0,
    act_cost_total_used_money numeric(32,16) NOT NULL DEFAULT 0,

    additional_sim_id numeric(20,0) DEFAULT 0,
    additional_roaming_destination_id numeric(20,0) DEFAULT 0,

    operation_status varchar(5) DEFAULT 'RESVR',

    CONSTRAINT pk_iot_portal_tb_request_log
        PRIMARY KEY (request_log_id),

    CONSTRAINT iot_portal_tb_request_log_unique
        UNIQUE (session_id, session_req_num, rating_group)
);
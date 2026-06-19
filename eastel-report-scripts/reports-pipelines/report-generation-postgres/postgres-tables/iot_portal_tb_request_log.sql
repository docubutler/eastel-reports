-- Table: public.iot_portal_tb_request_log

-- DROP TABLE IF EXISTS public.iot_portal_tb_request_log;

CREATE TABLE IF NOT EXISTS public.iot_portal_tb_request_log
(
    request_log_id numeric(20,0) NOT NULL DEFAULT nextval('iot_portal_seq_request_log'::regclass),
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
    cr_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    up_user numeric(20,0) NOT NULL DEFAULT 0,
    up_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_status numeric(2,0) NOT NULL DEFAULT 0,
    display_order numeric(4,0) NOT NULL DEFAULT 0,
    req_type character varying(50) COLLATE pg_catalog."default",
    req_time timestamp without time zone,
    session_id character varying(300) COLLATE pg_catalog."default",
    session_req_num numeric(20,0),
    iccid character varying(50) COLLATE pg_catalog."default",
    msisdn character varying(50) COLLATE pg_catalog."default",
    imei character varying(50) COLLATE pg_catalog."default",
    imsi character varying(50) COLLATE pg_catalog."default",
    roaming_mccmnc character varying(50) COLLATE pg_catalog."default",
    rat_type character varying(50) COLLATE pg_catalog."default",
    init_granted_volume numeric(32,16),
    update_used_volume numeric(32,16),
    total_used_volume numeric(32,16),
    exchange_rate numeric(32,16),
    cost_currency_cd character varying(50) COLLATE pg_catalog."default",
    cost_exchange_rate numeric(32,16),
    price_currency_cd character varying(50) COLLATE pg_catalog."default",
    price_exchange_rate numeric(32,16),
    cost_init_granted_money numeric(32,16),
    cost_update_used_money numeric(32,16),
    cost_total_used_money numeric(32,16),
    price_init_granted_money numeric(32,16),
    price_update_used_money numeric(32,16),
    price_total_used_money numeric(32,16),
    validity_time numeric(8,0),
    rating_group character varying(50) COLLATE pg_catalog."default",
    user_location_info character varying(50) COLLATE pg_catalog."default",
    apn character varying(50) COLLATE pg_catalog."default",
    service_context character varying(50) COLLATE pg_catalog."default",
    charging_characteristic character varying(50) COLLATE pg_catalog."default",
    sgsn_address character varying(50) COLLATE pg_catalog."default",
    notes character varying(300) COLLATE pg_catalog."default",
    addon_imsi character varying(50) COLLATE pg_catalog."default",
    addon_msisdn character varying(50) COLLATE pg_catalog."default",
    service_type_sub_cd character varying(50) COLLATE pg_catalog."default",
    opposite_number character varying(50) COLLATE pg_catalog."default",
    roaming_destination_id numeric(20,0) NOT NULL DEFAULT 0,
    act_update_used_volume numeric(32,16) NOT NULL DEFAULT 0,
    act_total_used_volume numeric(32,16) NOT NULL DEFAULT 0,
    act_price_update_used_money numeric(32,16) NOT NULL DEFAULT 0,
    act_price_total_used_money numeric(32,16) NOT NULL DEFAULT 0,
    act_cost_update_used_money numeric(32,16) NOT NULL DEFAULT 0,
    act_cost_total_used_money numeric(32,16) NOT NULL DEFAULT 0,
    additional_sim_id numeric(20,0) DEFAULT 0,
    additional_roaming_destination_id numeric(20,0) DEFAULT 0,
    operation_status character varying(5) COLLATE pg_catalog."default" DEFAULT 'RESVR'::character varying,
    CONSTRAINT pk_iot_portal_tb_request_log PRIMARY KEY (request_log_id),
    CONSTRAINT iot_portal_tb_request_log_unique UNIQUE (session_id, session_req_num, rating_group)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.iot_portal_tb_request_log
    OWNER to anchorprod;

REVOKE ALL ON TABLE public.iot_portal_tb_request_log FROM anchor_readonly;

GRANT SELECT ON TABLE public.iot_portal_tb_request_log TO anchor_readonly;

GRANT ALL ON TABLE public.iot_portal_tb_request_log TO anchorprod;

COMMENT ON TABLE public.iot_portal_tb_request_log
    IS '请求日志表';

COMMENT ON COLUMN public.iot_portal_tb_request_log.request_log_id
    IS '请求日志编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.currency_id
    IS '货币编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.service_type_id
    IS '服务类型编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.service_provider_id
    IS '服务提供商编号';

COMMENT ON COLUMN public.iot_portal_tb_request_log.rate_plan_id
    IS '费率计划编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.account_id
    IS '账户编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.sim_id
    IS 'sim卡编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.sim_service_plan_id
    IS 'sim卡服务计划编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.customer_id
    IS '客户编码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.user_id
    IS '用户id';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cr_user
    IS '新建用户';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cr_time
    IS '新建时间';

COMMENT ON COLUMN public.iot_portal_tb_request_log.up_user
    IS '更新用户';

COMMENT ON COLUMN public.iot_portal_tb_request_log.up_time
    IS '更新时间';

COMMENT ON COLUMN public.iot_portal_tb_request_log.record_status
    IS '记录状态';

COMMENT ON COLUMN public.iot_portal_tb_request_log.display_order
    IS '排序';

COMMENT ON COLUMN public.iot_portal_tb_request_log.req_type
    IS '请求类型';

COMMENT ON COLUMN public.iot_portal_tb_request_log.req_time
    IS '请求时间';

COMMENT ON COLUMN public.iot_portal_tb_request_log.session_id
    IS '会话';

COMMENT ON COLUMN public.iot_portal_tb_request_log.session_req_num
    IS '会话请求号';

COMMENT ON COLUMN public.iot_portal_tb_request_log.iccid
    IS 'ic卡识别码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.msisdn
    IS '手机号码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.imei
    IS '国际移动设备识别码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.imsi
    IS '国际移动用户识别码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.roaming_mccmnc
    IS '漫游移动码';

COMMENT ON COLUMN public.iot_portal_tb_request_log.rat_type
    IS '费率类型';

COMMENT ON COLUMN public.iot_portal_tb_request_log.init_granted_volume
    IS '初始化数量';

COMMENT ON COLUMN public.iot_portal_tb_request_log.update_used_volume
    IS '更新使用量';

COMMENT ON COLUMN public.iot_portal_tb_request_log.total_used_volume
    IS '总使用量';

COMMENT ON COLUMN public.iot_portal_tb_request_log.exchange_rate
    IS '变换汇率';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cost_currency_cd
    IS 'cost_currency_code';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cost_exchange_rate
    IS 'cost_exchange_rate';

COMMENT ON COLUMN public.iot_portal_tb_request_log.price_currency_cd
    IS 'price_currency_code';

COMMENT ON COLUMN public.iot_portal_tb_request_log.price_exchange_rate
    IS 'price_exchange_rate';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cost_init_granted_money
    IS 'cost_init_granted_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cost_update_used_money
    IS 'cost_uptimestamp_used_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.cost_total_used_money
    IS 'cost_total_used_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.price_init_granted_money
    IS 'price_init_granted_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.price_update_used_money
    IS 'price_uptimestamp_used_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.price_total_used_money
    IS 'price_total_used_money';

COMMENT ON COLUMN public.iot_portal_tb_request_log.validity_time
    IS '有效时间';

COMMENT ON COLUMN public.iot_portal_tb_request_log.rating_group
    IS 'rating_group';

COMMENT ON COLUMN public.iot_portal_tb_request_log.user_location_info
    IS 'user_location_info';

COMMENT ON COLUMN public.iot_portal_tb_request_log.apn
    IS 'apn';

COMMENT ON COLUMN public.iot_portal_tb_request_log.service_context
    IS 'service_context';

COMMENT ON COLUMN public.iot_portal_tb_request_log.charging_characteristic
    IS 'charging_characteristic';

COMMENT ON COLUMN public.iot_portal_tb_request_log.sgsn_address
    IS 'sgsn_address';

COMMENT ON COLUMN public.iot_portal_tb_request_log.notes
    IS 'notes';

COMMENT ON COLUMN public.iot_portal_tb_request_log.addon_imsi
    IS 'For OTA sim, the add-on imsi is using in this session';

COMMENT ON COLUMN public.iot_portal_tb_request_log.addon_msisdn
    IS 'For OTA sim, the add-on msisdn is using in this session';

COMMENT ON COLUMN public.iot_portal_tb_request_log.service_type_sub_cd
    IS 'service_type_sub_cd (N/A | MO | MT)';

COMMENT ON COLUMN public.iot_portal_tb_request_log.opposite_number
    IS 'For Voice call, showing opposite call party';

COMMENT ON COLUMN public.iot_portal_tb_request_log.additional_sim_id
    IS 'sim_id of additional number if the call is made by additional number';

COMMENT ON COLUMN public.iot_portal_tb_request_log.additional_roaming_destination_id
    IS 'roaming destination id according to additional sim rec';

COMMENT ON COLUMN public.iot_portal_tb_request_log.operation_status
    IS 'RESRV - Reserved, COMM - Committed';
-- Index: iot_portal_tb_request_log_account_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_account_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_account_id_idx
    ON public.iot_portal_tb_request_log USING btree
    (account_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_customer_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_customer_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_customer_id_idx
    ON public.iot_portal_tb_request_log USING btree
    (customer_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_iccid_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_iccid_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_iccid_idx
    ON public.iot_portal_tb_request_log USING btree
    (iccid COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_req_time_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_req_time_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_req_time_idx
    ON public.iot_portal_tb_request_log USING btree
    (req_time ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_req_type_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_req_type_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_req_type_idx
    ON public.iot_portal_tb_request_log USING btree
    (req_type COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_service_type_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_service_type_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_service_type_id_idx
    ON public.iot_portal_tb_request_log USING btree
    (service_type_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_session_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_session_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_session_id_idx
    ON public.iot_portal_tb_request_log USING btree
    (session_id COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_request_log_sim_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_request_log_sim_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_request_log_sim_id_idx
    ON public.iot_portal_tb_request_log USING btree
    (sim_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Trigger: trg_enqueue_request_log

-- DROP TRIGGER IF EXISTS trg_enqueue_request_log ON public.iot_portal_tb_request_log;

CREATE OR REPLACE TRIGGER trg_enqueue_request_log
    AFTER INSERT OR UPDATE 
    ON public.iot_portal_tb_request_log
    FOR EACH ROW
    EXECUTE FUNCTION public.enqueue_request_log();
-- Table: public.iot_portal_tb_usage_log

-- DROP TABLE IF EXISTS public.iot_portal_tb_usage_log;

CREATE TABLE IF NOT EXISTS public.iot_portal_tb_usage_log
(
    usage_log_id numeric(20,0) NOT NULL DEFAULT nextval('iot_portal_seq_usage_log'::regclass),
    rate_plan_id numeric(20,0) NOT NULL,
    currency_id numeric(20,0) NOT NULL,
    user_id numeric(20,0) NOT NULL,
    customer_id numeric(20,0) NOT NULL,
    sim_id numeric(20,0) NOT NULL,
    service_type_id numeric(20,0) NOT NULL,
    service_provider_id numeric(20,0) NOT NULL,
    sim_service_plan_id numeric(20,0) NOT NULL,
    account_id numeric(20,0) NOT NULL,
    cr_user numeric(20,0) NOT NULL DEFAULT 0,
    cr_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    up_user numeric(20,0) NOT NULL DEFAULT 0,
    up_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_status numeric(2,0) NOT NULL DEFAULT 0,
    last_session_req_num numeric(10,0) NOT NULL DEFAULT 0,
    session_id character varying(300) COLLATE pg_catalog."default" NOT NULL,
    iccid character varying(50) COLLATE pg_catalog."default" NOT NULL,
    msisdn character varying(50) COLLATE pg_catalog."default",
    imei character varying(50) COLLATE pg_catalog."default",
    imsi character varying(50) COLLATE pg_catalog."default",
    service_type_sub_cd character varying(50) COLLATE pg_catalog."default",
    roaming_mccmnc character varying(50) COLLATE pg_catalog."default",
    rat_type character varying(50) COLLATE pg_catalog."default",
    usage_unit numeric(32,16) NOT NULL DEFAULT 0,
    usage_start_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usage_update_time timestamp without time zone,
    usage_end_time timestamp without time zone,
    cost_amount numeric(32,16) NOT NULL DEFAULT 0,
    price_amount numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_quota_unit numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_cost_per_unit numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_quota_cost numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_price_per_unit numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_quota_price numeric(32,16) NOT NULL DEFAULT 0,
    addon_imsi character varying(50) COLLATE pg_catalog."default",
    addon_msisdn character varying(50) COLLATE pg_catalog."default",
    last_grant_shared_bucket_type_ids character varying(20) COLLATE pg_catalog."default" NOT NULL DEFAULT ''::character varying,
    opposite_number character varying(50) COLLATE pg_catalog."default",
    roaming_destination_id numeric(20,0) NOT NULL DEFAULT 0,
    act_usage_unit numeric(32,16) NOT NULL DEFAULT 0,
    act_cost_amount numeric(32,16) NOT NULL DEFAULT 0,
    act_price_amount numeric(32,16) NOT NULL DEFAULT 0,
    last_grant_vt numeric(20,0) NOT NULL DEFAULT 0,
    last_grant_sim_service_plan_id numeric(20,0) NOT NULL DEFAULT 0,
    last_grant_request_log_id numeric(20,0) NOT NULL DEFAULT 0,
    notes character varying(300) COLLATE pg_catalog."default",
    additional_sim_id numeric(20,0) NOT NULL DEFAULT 0,
    additional_roaming_destination_id numeric(20,0) NOT NULL DEFAULT 0,
    mt_sip_diverted numeric(2,0) NOT NULL DEFAULT 0,
    original_voice_call_type character varying(4) COLLATE pg_catalog."default",
    actual_opposite_number character varying(50) COLLATE pg_catalog."default",
    pdp_address character varying(20) COLLATE pg_catalog."default",
    last_grant_sim_service_plan_bucket_id numeric(20,0) NOT NULL DEFAULT 0,
    last_grant_sim_service_plan_bucket_start_ref timestamp without time zone,
    last_grant_sim_service_plan_detail_id numeric(20,0) NOT NULL DEFAULT 0,
    sim_master_id numeric(20,0) NOT NULL DEFAULT 0,
    rating_group character varying(50) COLLATE pg_catalog."default",
    traffic_rat character varying(50) COLLATE pg_catalog."default",
    last_grant_sim_service_plan_bucket_purchase_seq numeric(20,0),
    CONSTRAINT pk_iot_portal_tb_usage_log PRIMARY KEY (usage_log_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.iot_portal_tb_usage_log
    OWNER to anchorprod;

REVOKE ALL ON TABLE public.iot_portal_tb_usage_log FROM anchor_readonly;

GRANT SELECT ON TABLE public.iot_portal_tb_usage_log TO anchor_readonly;

GRANT ALL ON TABLE public.iot_portal_tb_usage_log TO anchorprod;

COMMENT ON TABLE public.iot_portal_tb_usage_log
    IS '使用日志表';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.usage_log_id
    IS '使用日志编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.rate_plan_id
    IS '费率计划编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.currency_id
    IS '货币编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.user_id
    IS '用户id';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.customer_id
    IS '客户编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.sim_id
    IS 'sim卡编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.service_type_id
    IS '服务类型编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.service_provider_id
    IS '服务提供商编号';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.sim_service_plan_id
    IS 'sim卡服务计划编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.account_id
    IS '账户编码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.cr_user
    IS '新建用户';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.cr_time
    IS '新建时间';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.up_user
    IS '更新用户';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.up_time
    IS '更新时间';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.record_status
    IS '记录状态';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_session_req_num
    IS 'last session request record number';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.session_id
    IS '会话';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.iccid
    IS 'ic卡识别码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.msisdn
    IS '手机号码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.imei
    IS '国际移动设备识别码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.imsi
    IS '国际移动用户识别码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.service_type_sub_cd
    IS 'service_type_sub_cd (N/A | MO | MT)';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.roaming_mccmnc
    IS '漫游移动码';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.rat_type
    IS '费率类型';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.usage_unit
    IS 'usage_unit';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.usage_start_time
    IS 'usage_start_time';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.usage_update_time
    IS 'usage_uptimestamp_time';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.usage_end_time
    IS 'usage_end_time';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.cost_amount
    IS 'cost_amount';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.price_amount
    IS 'price_amount';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_quota_unit
    IS 'Last granted units to user';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_cost_per_unit
    IS 'Cost rate for last granted units';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_quota_cost
    IS 'Cost of last granted units';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_price_per_unit
    IS 'Price rate for last granted units';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_quota_price
    IS 'Price of last granted units';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.addon_imsi
    IS 'For OTA sim, the add-on imsi is using in this session';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.addon_msisdn
    IS 'For OTA sim, the add-on msisdn is using in this session';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_shared_bucket_type_ids
    IS 'the shared bucket type IDs if bucket mode is share';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.opposite_number
    IS 'For Voice call, showing opposite call party';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_vt
    IS 'Last granted Validity Time';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_sim_service_plan_id
    IS 'Last sim service plan id for this session';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.last_grant_request_log_id
    IS 'Last granted Request log ID';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.notes
    IS 'Notes';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.additional_sim_id
    IS 'sim_id of additional number if the call is made by additional number';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.additional_roaming_destination_id
    IS 'roaming destination id according to additional sim rec';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.mt_sip_diverted
    IS 'Flag indicates if MT call was diverted to SIP';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.original_voice_call_type
    IS 'Mainly for discriminating forward leg charging on Update Charging';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.pdp_address
    IS 'PDP address (User device IP address)';

COMMENT ON COLUMN public.iot_portal_tb_usage_log.rating_group
    IS 'Rating group';
-- Index: iot_portal_tb_usage_log_iccid_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_usage_log_iccid_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_usage_log_iccid_idx
    ON public.iot_portal_tb_usage_log USING btree
    (iccid COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_usage_log_session_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_usage_log_session_id_idx;

CREATE UNIQUE INDEX IF NOT EXISTS iot_portal_tb_usage_log_session_id_idx
    ON public.iot_portal_tb_usage_log USING btree
    (session_id COLLATE pg_catalog."default" ASC NULLS LAST, rating_group COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_usage_log_sim_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_usage_log_sim_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_usage_log_sim_id_idx
    ON public.iot_portal_tb_usage_log USING btree
    (sim_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;

-- Trigger: trg_enqueue_usage_log

-- DROP TRIGGER IF EXISTS trg_enqueue_usage_log ON public.iot_portal_tb_usage_log;

CREATE OR REPLACE TRIGGER trg_enqueue_usage_log
    AFTER INSERT OR UPDATE 
    ON public.iot_portal_tb_usage_log
    FOR EACH ROW
    EXECUTE FUNCTION public.enqueue_usage_log();
-- Table: public.iot_portal_tb_country

-- DROP TABLE IF EXISTS public.iot_portal_tb_country;

CREATE TABLE IF NOT EXISTS public.iot_portal_tb_country
(
    country_id numeric(20,0) NOT NULL DEFAULT nextval('iot_portal_seq_country'::regclass),
    cr_user numeric(20,0) NOT NULL DEFAULT 0,
    cr_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    up_user numeric(20,0) NOT NULL DEFAULT 0,
    up_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_status numeric(2,0) NOT NULL DEFAULT 0,
    display_order numeric(4,0) NOT NULL DEFAULT 0,
    country_name character varying(64) COLLATE pg_catalog."default" NOT NULL,
    country_cd character varying(64) COLLATE pg_catalog."default" NOT NULL,
    mcc character varying(64) COLLATE pg_catalog."default" NOT NULL,
    cc character varying(64) COLLATE pg_catalog."default" NOT NULL,
    idd_call_prefix_list character varying(100) COLLATE pg_catalog."default" NOT NULL,
    local_call_prefix_list character varying(100) COLLATE pg_catalog."default",
    CONSTRAINT pk_iot_portal_tb_country PRIMARY KEY (country_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.iot_portal_tb_country
    OWNER to anchorprod;

REVOKE ALL ON TABLE public.iot_portal_tb_country FROM anchor_readonly;

GRANT SELECT ON TABLE public.iot_portal_tb_country TO anchor_readonly;

GRANT ALL ON TABLE public.iot_portal_tb_country TO anchorprod;

COMMENT ON TABLE public.iot_portal_tb_country
    IS '国家信息表';

COMMENT ON COLUMN public.iot_portal_tb_country.country_id
    IS '国家编码';

COMMENT ON COLUMN public.iot_portal_tb_country.cr_user
    IS '新建用户';

COMMENT ON COLUMN public.iot_portal_tb_country.cr_time
    IS '新建时间';

COMMENT ON COLUMN public.iot_portal_tb_country.up_user
    IS '更新用户';

COMMENT ON COLUMN public.iot_portal_tb_country.up_time
    IS '更新时间';

COMMENT ON COLUMN public.iot_portal_tb_country.record_status
    IS '记录状态';

COMMENT ON COLUMN public.iot_portal_tb_country.display_order
    IS '排序';

COMMENT ON COLUMN public.iot_portal_tb_country.country_name
    IS '国家名称';

COMMENT ON COLUMN public.iot_portal_tb_country.country_cd
    IS '国家编号';

COMMENT ON COLUMN public.iot_portal_tb_country.mcc
    IS '移动国家码';

COMMENT ON COLUMN public.iot_portal_tb_country.cc
    IS '国家码';

COMMENT ON COLUMN public.iot_portal_tb_country.idd_call_prefix_list
    IS 'International call prefix of the country listed as CSV';

COMMENT ON COLUMN public.iot_portal_tb_country.local_call_prefix_list
    IS 'Local call prefix  of the country listed as CSV';
-- Index: iot_portal_tb_country_country_cd_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_country_country_cd_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_country_country_cd_idx
    ON public.iot_portal_tb_country USING btree
    (country_cd COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Table: public.iot_portal_tb_roaming_destination

-- DROP TABLE IF EXISTS public.iot_portal_tb_roaming_destination;

CREATE TABLE IF NOT EXISTS public.iot_portal_tb_roaming_destination
(
    roaming_destination_id numeric(20,0) NOT NULL DEFAULT nextval('iot_portal_seq_roaming_destination'::regclass),
    service_provider_id numeric(20,0) NOT NULL,
    country_id numeric(20,0) NOT NULL DEFAULT 0,
    cr_user numeric(20,0) NOT NULL DEFAULT 0,
    cr_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    up_user numeric(20,0) NOT NULL DEFAULT 0,
    up_time timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_status numeric(2,0) NOT NULL DEFAULT 0,
    display_order numeric(4,0) NOT NULL DEFAULT 0,
    roaming_destination_name character varying(100) COLLATE pg_catalog."default" NOT NULL,
    mcc character varying(10) COLLATE pg_catalog."default",
    remarks character varying(300) COLLATE pg_catalog."default",
    tadig character varying(10) COLLATE pg_catalog."default",
    operator character varying(200) COLLATE pg_catalog."default",
    CONSTRAINT iot_portal_tb_roaming_destination_pk PRIMARY KEY (roaming_destination_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.iot_portal_tb_roaming_destination
    OWNER to anchorprod;

REVOKE ALL ON TABLE public.iot_portal_tb_roaming_destination FROM anchor_readonly;

GRANT SELECT ON TABLE public.iot_portal_tb_roaming_destination TO anchor_readonly;

GRANT ALL ON TABLE public.iot_portal_tb_roaming_destination TO anchorprod;
-- Index: iot_portal_tb_roaming_destination_service_provider_id_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_roaming_destination_service_provider_id_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_roaming_destination_service_provider_id_idx
    ON public.iot_portal_tb_roaming_destination USING btree
    (service_provider_id ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
-- Index: iot_portal_tb_roaming_destination_service_provider_id_oper_idx

-- DROP INDEX IF EXISTS public.iot_portal_tb_roaming_destination_service_provider_id_oper_idx;

CREATE INDEX IF NOT EXISTS iot_portal_tb_roaming_destination_service_provider_id_oper_idx
    ON public.iot_portal_tb_roaming_destination USING btree
    (service_provider_id ASC NULLS LAST, country_id ASC NULLS LAST, roaming_destination_name COLLATE pg_catalog."default" ASC NULLS LAST)
    WITH (fillfactor=100, deduplicate_items=True)
    TABLESPACE pg_default;
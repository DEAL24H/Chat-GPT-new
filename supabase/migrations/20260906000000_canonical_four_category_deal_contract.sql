DO $$
DECLARE
  nonzero bigint;
BEGIN
  SELECT count(*) INTO nonzero FROM public.deals;
  IF nonzero <> 0 THEN
    RAISE EXCEPTION 'Refusing canonical category migration: public.deals contains % rows', nonzero;
  END IF;
END $$;

ALTER TABLE public.deals
  ADD COLUMN IF NOT EXISTS final_purchase_url text,
  ADD COLUMN IF NOT EXISTS source_verification_status text,
  ADD COLUMN IF NOT EXISTS source_verification_authority text,
  ADD COLUMN IF NOT EXISTS purchase_url_verification_status text,
  ADD COLUMN IF NOT EXISTS purchase_url_verification_reason text,
  ADD COLUMN IF NOT EXISTS purchase_url_verified_at timestamptz;

DROP TABLE IF EXISTS public.deals_fashion CASCADE;
DROP TABLE IF EXISTS public.deals_dien_tu_gia_dung CASCADE;
DROP TABLE IF EXISTS public.deals_hang_tieu_dung CASCADE;
DROP TABLE IF EXISTS public.deals_thuc_pham_gia_vi CASCADE;

CREATE TABLE public.deals_fashion PARTITION OF public.deals FOR VALUES IN ('Fashion');
CREATE TABLE public.deals_electronics PARTITION OF public.deals FOR VALUES IN ('Electronics');
CREATE TABLE public.deals_beauty_personal_care PARTITION OF public.deals FOR VALUES IN ('Beauty & Personal Care');
CREATE TABLE public.deals_home_living PARTITION OF public.deals FOR VALUES IN ('Home & Living');

ALTER TABLE public.deals
  DROP CONSTRAINT IF EXISTS deals_source_verification_status_check,
  DROP CONSTRAINT IF EXISTS deals_purchase_url_verification_status_check;

ALTER TABLE public.deals
  ADD CONSTRAINT deals_source_verification_status_check
  CHECK (source_verification_status IS NULL OR source_verification_status = 'assistant_verified_first_party'),
  ADD CONSTRAINT deals_purchase_url_verification_status_check
  CHECK (purchase_url_verification_status IS NULL OR purchase_url_verification_status IN ('live_verified','runtime_inaccessible'));

CREATE INDEX IF NOT EXISTS deals_final_purchase_url_idx ON public.deals (final_purchase_url);
CREATE INDEX IF NOT EXISTS deals_purchase_verification_idx ON public.deals (purchase_url_verification_status, status);

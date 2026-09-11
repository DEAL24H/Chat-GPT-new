-- Keep official same-domain offers when a merchant temporarily times out.
-- The destination remains constrained to the official source domain by the
-- application contract; this status means only that live verification is pending.
ALTER TABLE public.deals
  DROP CONSTRAINT IF EXISTS deals_purchase_url_verification_status_check;

ALTER TABLE public.deals
  ADD CONSTRAINT deals_purchase_url_verification_status_check
  CHECK (purchase_url_verification_status IN ('live_verified', 'official_destination_pending'));

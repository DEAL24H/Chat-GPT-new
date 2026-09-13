-- Bind every canonical Supabase row to the same immutable release as GitHub Pages.
ALTER TABLE public.deals
  ADD COLUMN IF NOT EXISTS release_id text;
CREATE INDEX IF NOT EXISTS deals_release_id_idx ON public.deals (release_id);
COMMENT ON COLUMN public.deals.release_id IS 'Deal24h canonical publication release_id shared with static data, SEO pages, sitemaps, and UI.';

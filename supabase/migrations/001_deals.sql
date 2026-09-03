create table if not exists public.deals (
  id text not null,
  merchant text not null,
  category text not null,
  country text,
  title text,
  content text,
  code text,
  discount text,
  promotion_url text,
  source_url text,
  source_domain text,
  official_source boolean not null default false,
  status text not null default 'active',
  expires_at timestamptz,
  detected_at timestamptz,
  last_checked timestamptz,
  updated_at timestamptz not null default now(),
  search_text tsvector generated always as (to_tsvector('simple', coalesce(merchant,'') || ' ' || coalesce(title,'') || ' ' || coalesce(content,'') || ' ' || coalesce(code,'') || ' ' || coalesce(category,''))) stored,
  primary key (category, id)
) partition by list (category);
create table if not exists public.deals_fashion partition of public.deals for values in ('Fashion');
create table if not exists public.deals_beauty partition of public.deals for values in ('Beauty');
create table if not exists public.deals_consumer partition of public.deals for values in ('Consumer');
create table if not exists public.deals_home_living partition of public.deals for values in ('Home & Living');
create table if not exists public.deals_food_grocery partition of public.deals for values in ('Food & Grocery');
create table if not exists public.deals_travel_hotels partition of public.deals for values in ('Travel & Hotels');
create index if not exists deals_search_idx on public.deals using gin (search_text);
create index if not exists deals_merchant_idx on public.deals (merchant);
create index if not exists deals_status_expiry_idx on public.deals (status, expires_at);
alter table public.deals enable row level security;
drop policy if exists "public can read active deals" on public.deals;
create policy "public can read active deals" on public.deals for select using (status = 'active' and (expires_at is null or expires_at > now()));
comment on table public.deals is 'DEAL24H canonical offer store; category partitions bound query cost as the catalog grows.';

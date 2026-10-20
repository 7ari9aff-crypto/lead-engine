-- Stripe attribution: lets customer.subscription.* events (which carry only
-- customer/subscription ids) be mapped back to the organization.
alter table public.organizations
  add column if not exists stripe_customer_id text,
  add column if not exists stripe_subscription_id text;

create index if not exists organizations_stripe_customer_idx
  on public.organizations (stripe_customer_id) where stripe_customer_id is not null;
create index if not exists organizations_stripe_subscription_idx
  on public.organizations (stripe_subscription_id) where stripe_subscription_id is not null;

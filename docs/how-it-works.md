# How pensionTracker works

A plain-English walkthrough of what the system does. It grows as features land.

## Today: a single web page

When you visit the site's address, your browser asks **CloudFront** for the page.
CloudFront is Amazon's worldwide network of servers that sit close to visitors
and hand out web pages quickly.

CloudFront doesn't store the page itself. It fetches it from an **S3 bucket**, a
private storage area in Amazon's Ireland region, and keeps a copy for next time.
The bucket isn't open to the public: only CloudFront is allowed to read from it,
so the only way to see the page is through the proper web address.

The connection is always encrypted (the padlock in your browser). The
certificate that proves the site is genuine is issued and renewed automatically
by Amazon. If someone types `http://` instead of `https://`, they're sent to the
secure version.

All of this is described in Python code in the `infra/` folder. That code
produces the instructions (CloudFormation templates) that tell AWS what to
create, so the whole setup can be rebuilt from scratch with one command.

A budget alarm emails the owner if the monthly AWS bill starts creeping up.

### Two copies: dev and prod

There are two separate copies of the site, built from the same code:

- **prod** (`pensiontrackerapp.com`) is the real one that visitors see.
- **dev** (`dev.pensiontrackerapp.com`) is a practice copy. Changes are tried
  there first, and only reach prod once they've been checked. It tells search
  engines not to list it, so people searching the web only find the real site.

Each copy has its own storage, its own CloudFront setup and its own certificate,
so nothing done to dev can affect prod. Every deployment command has to name
which copy it's for; leaving it out is an error, so the real site can't be
changed by accident.

## Coming next

Signing in, adding pension pots, recording valuations and seeing projections.
See [`plan.md`](plan.md).

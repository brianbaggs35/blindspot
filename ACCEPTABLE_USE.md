# Acceptable use

Blindspot is a security testing tool. It is built for people who are allowed to test the systems
they point it at. Read the [terms of use](DISCLAIMER.md) first; this page says what that means in
practice. It is not legal advice.

## You may

- Test systems you own.
- Test systems whose owner has given you written permission that names the target, the kinds of
  testing and the dates. Keep that permission with the pentest (Blindspot can store the signed
  letter) and keep to it.
- Test your own lab, a deliberately vulnerable practice application, or a capture-the-flag
  environment that invites attacks.
- Use the findings to fix weaknesses and to write reports for the owner.

## You may not

- Test a system without its owner's permission, or beyond what that permission covers.
- Test shared infrastructure (a cloud provider's own services, a hosting company's network, a
  third party's API) unless that party's rules allow it. Read the provider's testing policy first.
- Use Blindspot to deny service, to steal or leak data, to take over accounts, or to harm anybody.
- Point Blindspot at systems that hold other people's data you are not entitled to see, or send
  that data to an AI provider you do not have the right to send it to.
- Remove or work around the scope checks, the authorization step or the audit log.

## Before every pentest

1. Get the permission in writing and check it covers the target and the dates.
2. Put exactly what is covered in scope, and what is not in out of scope.
3. Tell the people who run the target when testing will happen, and who to call if something goes
   wrong.
4. Prefer a test copy of the system. Take a backup of anything that matters.
5. Choose the lowest level of testing that answers your question, and read what a pentest will do
   before you press Start.

## If something goes wrong

Pause or stop the pentest, then tell the owner of the system straight away. Keep the audit log: it
records what Blindspot did and when.

-- Language of the screens per user (en, de). NULL: the switch on the sign-in pages, the site default or the browser decides.
ALTER TABLE users
  ADD COLUMN lang VARCHAR(5) NULL AFTER timezone;

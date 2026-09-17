# Redaction check

The known-bad and known-clean cases every redaction path must pass before
a corpus record is written. `scripts/redact.py` is tested against this
file, and the no-Python path redacts every case here by hand before its
first write, as the setup collect step describes.

## Format

One case per line in the fenced block: the input, then ` ==> `, then the
exact expected output. Every input has the text `{join}` inside its
secret so that this file itself never matches a secret scan; delete each
`{join}` before redacting. Expected outputs contain no `{join}`.

A path passes when every input, with `{join}` removed, redacts to exactly
its expected output. One miss fails the whole check.

## Cases

```redaction-check
the key is -----BEGIN RSA PRIV{join}ATE KEY----- MIIEow {join}IBAAKCAQEA -----END RSA PRIVATE KEY----- rotate it ==> the key is <redacted:private-key> rotate it
set api_{join}key = "abcdefghijklmnopqrstuvwxyz123456" in the config ==> set <redacted:keyed-assignment> in the config
pass{join}word: "hunter2hunter2" was in the log ==> <redacted:password> was in the log
client 1234567890abcdef1234567890abcdef.apps.google{join}usercontent.com is ours ==> client <redacted:google-oauth-client-id> is ours
the id AKIA{join}ABCDEFGHIJKLMNOP leaked ==> the id <redacted:aws-access-key-id> leaked
aws_secret_access_{join}key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYAB ==> <redacted:aws-secret-access-key>
bot token xox{join}b-1234567890-abcdefghij works ==> bot token <redacted:slack-token> works
use ghp_{join}0123456789abcdefghijklmnopqrstuvwxyz for now ==> use <redacted:github-pat> for now
use github_pat_{join}0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghij for now ==> use <redacted:github-fine-grained-pat> for now
Server=db1;Database=x;User Id=sa;Pass{join}word=Sup3rS3cret; is the string ==> <redacted:connection-string>; is the string
mongo{join}db://admin:pa55word@cluster0 is prod ==> <redacted:mongodb-connection-string>cluster0 is prod
post{join}gres://app:pa55word@db:5432/x is staging ==> <redacted:postgres-connection-string>db:5432/x is staging
the retry policy stops at 3 attempts ==> the retry policy stops at 3 attempts
see https://example.com/docs for the password reset flow ==> see https://example.com/docs for the password reset flow
join https://zoom.us/j/81234567890?p{join}wd=Xy7Qa9LmNpRsTuVw.1 at noon ==> join https://zoom.us/j/81234567890?pwd=<redacted:password> at noon
Set-Coo{join}kie: cart_id=8f3a2b1c9d7e; Path=/; HttpOnly ==> Set-Cookie: <redacted:cookie>
curl -H 'coo{join}kie: theme=dark; cart_id=8f3a2b1c9d7e' https://api.example.com/v1 ==> curl -H 'cookie: <redacted:cookie>
the _cfu{join}vid=Qm9vZ2xlQ29va2llVmFsdWU1 cookie again ==> the _cfuvid=<redacted:cookie> cookie again
curl -b 'PHPSESS{join}ID=9f8e7d6c5b4a3f2e; theme=dark' https://example.com ==> curl -b 'PHPSESSID=<redacted:cookie>; theme=dark' https://example.com
Authorization: Bea{join}rer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij ==> Authorization: Bearer <redacted:token>
retry with Bea{join}rer abcdefghijklmnopqrstuvwx0123 and it works ==> retry with Bearer <redacted:token> and it works
Authorization: Bea{join}rer ghp_{join}0123456789abcdefghijklmnopqrstuvwxyz ==> Authorization: Bearer <redacted:github-pat>
the cookie: chocolate chip, and he is the bearer of good news ==> the cookie: chocolate chip, and he is the bearer of good news
start a new pairing session=today and a sessionid=42 debug run ==> start a new pairing session=today and a sessionid=42 debug run
```

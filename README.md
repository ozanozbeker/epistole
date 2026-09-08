# herma

A single Python API for sending email, regardless of the backend.

`herma` takes an email you have already composed as HTML and sends it through whichever service you have configured, using the same interface each time.
Supported backends are SMTP, Microsoft Graph, and Google, with room for more.
Switching providers means changing configuration, not rewriting your code.

This is an early project and the API is not yet stable.

## About the name

A herma was a stone marker set at crossroads and roadsides in ancient Greece.
Travelers used them to tell which road led where.
The name fits a library whose job is to take one message and direct it down whichever road you have chosen.

## Credit

`herma` is inspired by [blastula](https://github.com/rstudio/blastula), an R package for composing and sending email.
It is not a port, and the API does not mirror blastula's.

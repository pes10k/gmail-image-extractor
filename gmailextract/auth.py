"""

Handles Oauth2 specific intitlization and oauth configuration.  We rely on
Google's provided OAuth2 client library to do the communication and validation
for us, but this module handles common initilization needs.

"""

from oauth2client.client import OAuth2WebServerFlow
from utilities import loop_cb_args
from tornado import httpclient
import urllib
import json
import config


# If things are configured to dump all network traffic, configure the
# Tornado provided Async HTTP classes to use our verbose logging
# subclass
if config.stress_test_record and config.netdump_path:
    from profiling import SimpleAsyncHTTPClient_Netdump
    httpclient.AsyncHTTPClient.configure(SimpleAsyncHTTPClient_Netdump)
elif config.stress_test_run:
    from stress_test import SimpleAsyncHTTPClient_Stresstest
    httpclient.AsyncHTTPClient.configure(SimpleAsyncHTTPClient_Stresstest)


def gmail_oauth_flow(state=None):
    """Returns a OAuth2 Flow object for authentiating users with GMail

    @See https://developers.google.com/api-client-library/python/guide/aaa_oauth#step1_get_authorize_url

    Keyword Args:
        state  -- Values to return to end point

    Returns:
        A populated Flow object, provided by the Google OAuth2 client library
    """
    redirect_uri = config.base_url + "/oauth2"

    args = dict(
        client_id=config.oauth2_client_id,
        client_secret=config.oauth2_client_secret,
        scope=["https://mail.google.com/",
               "https://www.googleapis.com/auth/userinfo.email"],
        redirect_uri=redirect_uri,
        access_type="online",
        response_type="code"
    )

    if state:
        args['state'] = json.dumps(state)

    return OAuth2WebServerFlow(**args)


def validate_oauth_response(oauth_response, callback=None):
    """Checks to see whether a given OAuth2 response is authentic by validating
    its containing access_token with Google's Oauth2 service

    Args:
        oauth_response -- A dictionary of parameters representing an Oauth2
                          response from Google.  Must contain at least an
                          "access_token" key

    Returns:
        The valid oauth_response if the contained access_token is valid, and
        False in all other cases
    """
    def _validation_completed(validation_response):
        if validation_response.error:
            is_token_valid = False
        else:
            validation_data = json.loads(validation_response.body)
            try:
                is_token_valid = validation_data["expires_in"] > 0
            except KeyError:
                is_token_valid = False
            loop_cb_args(callback, oauth_response if is_token_valid else False)

    try:
        access_token = oauth_response['access_token']
    except KeyError:
        access_token = None

    if access_token:
        validate_client = httpclient.AsyncHTTPClient()
        validate_client.fetch(
            "https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=" + access_token,
            _validation_completed
        )
    else:
        loop_cb_args(callback, False)


def oauth_token_swap(oauth_token, callback=None):
    """Returns the oauth2 response parameters from Google / Gmail, given the
    initial oauth token.

    Args:
        oauth_token -- The oauth token returned from Gmail, to be returned
                       to Gmail / google to fetch an access token

    Returns:
        A dict of the Google populated Oauth2 response on success, and None
        in all other situaitons
    """

    def _on_access_token(response):
        if response.error:
            loop_cb_args(callback, None)
        else:
            oauth_response = json.loads(response.body)
            if "access_token" not in oauth_response:
                # If the Gmail Oauth response doesn't include an access token
                # at all, it means something application layer went wrong
                # and we should bail out
                loop_cb_args(callback, None)
            else:
                validate_oauth_response(oauth_response, callback=callback)

    args = dict(
        redirect_uri=config.base_url + "/oauth2",
        client_id=config.oauth2_client_id,
        client_secret=config.oauth2_client_secret,
        code=oauth_token,
        grant_type="authorization_code"
    )

    request = httpclient.HTTPRequest("https://accounts.google.com/o/oauth2/token",
                                     method="POST", body=urllib.urlencode(args))
    client = httpclient.AsyncHTTPClient()
    client.fetch(request, _on_access_token)


def email_for_token(access_token, callback=None):
    """Returns the email address validated with the oauth2 access token

    Args:
        access_token -- A Gmail oauth access token that includes the
                        https://www.googleapis.com/auth/userinfo.email scope

    Returns:
        A string email address associated with the token, or None if no
        email address is available
    """
    def _on_response(email_response):
        if email_response.error:
            loop_cb_args(callback, None)
        else:
            email_data = json.loads(email_response.body, strict=False)
            try:
                email_address = email_data["data"]["email"]
            except KeyError:
                email_address = None
            loop_cb_args(callback, email_address)

    client = httpclient.AsyncHTTPClient()
    client.fetch(
        "https://www.googleapis.com/userinfo/email?alt=json&access_token=" + access_token,
        _on_response
    )

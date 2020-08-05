from django.conf import settings
from django.contrib import auth
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.urls import reverse

from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
from requests_oauthlib import OAuth2Session

from . import (
    _CLIENT_ID_SETTING,
    _CLIENT_SECRET_SETTING,
)

STATE_SESSION_KEY = 'oauth-state'
_DEFAULT_OAUTH_SCOPES = [
    "openid",
    "profile",
    "email"
]
AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://www.googleapis.com/oauth2/v4/token"

GOOGLE_USER_INFO = "https://www.googleapis.com/oauth2/v1/userinfo"

_DEFAULT_WHITELISTED_SCOPES = _DEFAULT_OAUTH_SCOPES[:]


def _get_scopes(request_scopes):
    if not request_scopes:
        return getattr(settings, "GOOGLEAUTH_OAUTH_SCOPES", _DEFAULT_OAUTH_SCOPES)
        return _DEFAULT_WHITELISTED_SCOPES
    else:
        parsed_scopes = request_scopes.split(',')
        WHITELISTED_SCOPES = getattr(settings, "GOOGLE_OAUTH_SCOPE_WHITELIST", _DEFAULT_WHITELISTED_SCOPES)
        if set(parsed_scopes) - set(WHITELISTED_SCOPES) != set():
            raise Http404("Not all scopes were whitelisted for the application.")
        return parsed_scopes


def login(request):
    """
        This view should be set as your login_url for using OAuth
        authentication. It will trigger the main oauth flow.
    """
    original_url = f"{request.scheme}://{request.META['HTTP_HOST']}{reverse('googleauth_oauth2callback')}"
    scopes = _get_scopes(request.GET.get('scopes'))
    next_url = request.GET.get('next')

    if next_url:
        request.session[auth.REDIRECT_FIELD_NAME] = next_url

    client_id = getattr(settings, _CLIENT_ID_SETTING)
    assert client_id

    google = OAuth2Session(client_id, scope=scopes, redirect_uri=original_url)
    authorization_url, state = google.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type="offline",
        prompt="select_account"
    )
    request.session[STATE_SESSION_KEY] = state

    return HttpResponseRedirect(authorization_url)


def oauth2callback(request):

    original_url = f"{request.scheme}://{request.META['HTTP_HOST']}{reverse('googleauth_oauth2callback')}"

    if STATE_SESSION_KEY not in request.session:
        return HttpResponseBadRequest()

    client_id = getattr(settings, _CLIENT_ID_SETTING)
    client_secret = getattr(settings, _CLIENT_SECRET_SETTING)

    assert client_id and client_secret

    google = OAuth2Session(
        client_id,
        state=request.session[STATE_SESSION_KEY],
        redirect_uri=original_url
    )

    token = {}
    try:
        token = google.fetch_token(
            TOKEN_URL,
            client_secret=client_secret,
            authorization_response=request.build_absolute_uri()
        )
    except MismatchingStateError:
        return HttpResponseBadRequest()

    next_url = request.session[auth.REDIRECT_FIELD_NAME]
    if google.authorized and next_url:
        r = google.get(GOOGLE_USER_INFO)
        raw_user = r.json()
        # credentials are valid, we should authenticate the user
        user = auth.authenticate(request, username=raw_user.get('id'), email=raw_user.get('email'), token=token)
        auth.login(request, user)
        return HttpResponseRedirect(next_url)

    return HttpResponseRedirect(reverse("googleauth_oauth2login"))

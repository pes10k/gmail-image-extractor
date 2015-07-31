from pywebassets import assets
from drano.forms import survey_form
from drano.auth import oauth_token_swap, gmail_oauth_flow, email_for_token
from drano.utilities import add_loop_cb, add_loop_cb_args, loop_cb_args
from drano.debugging import test_messages
from tornado.log import app_log, gen_log
import time
import pygmail.errors
import drano.common
import drano.helpers
import tornado.web
import drano.database as DB
import drano.gen
import drano.users
import config
import json
import re
import uuid


class DranoRequestHandler(tornado.web.RequestHandler):

    def prepare(self):
        # If we're not in debugging mode (ie we're in "production"),
        # send down HTTP Strict Transport Security header to make sure
        # we're only visited via https
        if not config.debug:
            self.set_header('Strict-Transport-Security',
                            'max-age=16070400; includeSubDomains')

        if config.stress_test_run:
            if not self.get_secure_cookie('drano_user'):
                self.set_secure_cookie('drano_user', 'stress-test')
            if not self.get_secure_cookie('email'):
                self.set_secure_cookie('email', config.devel_oauth_credentials['email'])
            if not self.get_secure_cookie('mplex_sess'):
                self.set_secure_cookie('mplex_sess', unicode(uuid.uuid4()))

        super(DranoRequestHandler, self).prepare()

    def render(self, template, **kwords):
        """Render a template

        We override the the render method so that we can inject any
        message information (provided by the ?msg=# parameter) into the
        templates automatically.

        """
        warning_message = self.get_argument('msg-error', None)
        if warning_message:
            warning_message = drano.common.error_msg(warning_message)

        info_message = self.get_argument('msg-info', None)
        if info_message:
            info_message = drano.common.error_msg(info_message)

        if 'user' not in kwords:
            kwords['user'] = None

        kwords['config'] = config
        kwords["warning_message"] = warning_message
        kwords["info_message"] = info_message
        kwords['js'] = assets.JavascriptAssets(devel=config.debug)
        kwords['css'] = assets.CssAssets(devel=config.debug)
        kwords['helpers'] = drano.helpers
        kwords['mplex_sess'] = self.get_secure_cookie('mplex_sess') or None

        # For styling / themeing reasons, add a simple class to the body
        # element on each page that matches the current URL
        body_class = re.sub("[^\w\-]", "-", self.request.uri).strip("-") or "front"
        kwords['body_class'] = "page-" + body_class

        return super(DranoRequestHandler, self).render(template, **kwords)

    def oauth_flow(self, url=None, **kwords):
        url = url or self.request.uri
        state = dict(url=url, **kwords)
        flow = gmail_oauth_flow(state=state)
        authorize_url = flow.step1_get_authorize_url()
        self.redirect(authorize_url)


class Static(DranoRequestHandler):

    PAGES = {
        "privacy": "Privacy Policy",
        "faq": "Frequently Asked Questions",
        "audit": "Audit",
        "search": "Search",
        "password-pii-value-study": "Password/PII Value Study",
        "phishing-study": "UIC Phishing Security Study"
    }

    def get(self, page):
        page_title = Static.PAGES[page]
        page_name = "static/{page}.html".format(page=page)
        self.render(page_name, page_title=page_title, page=page)


class Landing(DranoRequestHandler):
    """Request handler for the landing page

    The landing page includes two items:
        - lots of text, describing the project / purpose, etc, and
        - a form for authenticating with google.  This is done with a form
          (instead of just a link to the OAuth callback end point), so that
          we can capture whether the user wants to be included in the research
          gathering set of users

    """

    @drano.gen.load_user()
    def get(self, user):
        self.render("landing/get.html", user=user)

    def post(self):
        """Post handler to respond to the 'connect to google request' button

        We add this level of indirection in to the OAuth2 redirection
        so that we can start a session for the user and keep track
        of whether they opt into data collection.  This POST request
        will never generate markup.

        """
        should_include = self.get_argument("include", False)
        action = self.get_argument('action', False)

        if action not in drano.common.ACTIONS:
            self.redirect("/?msg-error=7")
        elif should_include:
            self.redirect("/consent?action=" + action)
        elif config.stress_test_run and config.devel_oauth_credentials:
            self.redirect(drano.common.ACTIONS[action])
        else:
            self.oauth_flow(tracking=False)


class Consent(DranoRequestHandler):

    @drano.gen.load_user()
    def get(self, user=None):
        action = self.get_argument('action', False)
        if action not in drano.common.ACTIONS:
            self.redirect("/?msg-error=7")
        else:
            self.render("consent/get.html", action=action, user=user)

    def post(self):
        action = self.get_argument('action', False)

        try:
            url = drano.common.ACTIONS[action]
        except KeyError:
            raise tornado.web.HTTPError(404)

        if config.stress_test_run and config.devel_oauth_credentials:
            self.redirect(url)
        else:
            self.oauth_flow(tracking=True, url=url)


class Authorize(DranoRequestHandler):
    """Handle requests coming from google from OAuth2 requests

    If we're here there are several possibilities:
        - Successful OAuth connections
            authenticate tokens with google and direct user to their mailboxes
        - Rejected OAuth connections
            kick them back to the homepage with an error flag.  Close all
            sessions
        - all other connections
            Raise 404
    """
    @drano.gen.load_user()
    def get(self, user=None):
        error = self.get_argument("error", False)
        code = self.get_argument("code", False)
        state = self.get_argument('state', False)

        if state:
            state = json.loads(state.replace(r"'", r'"'), strict=False)

        def _redirect_response(new_user):
            if state and 'url' in state:
                if 'tracking' in state:
                    new_user.tracking = state['tracking']
                self.redirect(state['url'])
            else:
                self.redirect("/?msg-error=1")

        def _find_trash_mailbox(trash_mailbox, new_user, account):
            if not trash_mailbox or pygmail.errors.is_error(trash_mailbox):
                self.redirect("/?msg-error=9")
            else:
                new_user.trash_folder = trash_mailbox.name
                new_user.close_gmail(_redirect_response)

        def _find_all_mailbox(all_mailbox, new_user, account):
            if not all_mailbox or pygmail.errors.is_error(all_mailbox):
                self.redirect("/?msg-error=8")
            else:
                new_user.all_folder = all_mailbox.name
                cbp = dict(new_user=new_user, account=account)
                cp = add_loop_cb_args(_find_trash_mailbox, cbp)
                account.trash_mailbox(callback=cp)

        def _with_connection(rs):
            new_user, account = rs
            cbp = dict(new_user=new_user, account=account)
            cb = add_loop_cb_args(_find_all_mailbox, cbp)
            account.all_mailbox(callback=cb)

        def _on_new_user(new_user, oauth_data=None):
            new_user.access_token = oauth_data['access_token']
            new_user.set_sec_till_expiration(oauth_data['expires_in'])
            self.set_secure_cookie('drano_user', new_user.token)
            self.set_secure_cookie('email', new_user.email)
            new_user.get_gmail(callback=_with_connection)

        def _email_for_token_complete(email, oauth_data=None):
            cbp = dict(oauth_data=oauth_data)
            cb = add_loop_cb_args(_on_new_user, cbp)
            if config.stress_test_run:
                sess_id = self.get_secure_cookie('mplex_sess') or None
            else:
                sess_id = None
            drano.users.User.new(email, callback=cb, identifier=sess_id)

        def _on_token_swap(oauth_data):
            if not oauth_data:
                self.redirect("/?msg-error=1")
            else:
                if not user:
                    # If we already have the current user's email address,
                    # we can just redirect the user to their end point.
                    # Otherwise, we grab the user's email address before doing
                    # the same.
                    cbp = dict(oauth_data=oauth_data)
                    cb = add_loop_cb_args(_email_for_token_complete, cbp)
                    email_for_token(oauth_data['access_token'], callback=cb)
                else:
                    user.access_token = oauth_data['access_token']
                    user.set_sec_till_expiration(oauth_data['expires_in'])
                    loop_cb_args(_redirect_response, user)

        if error:
            gen_log.error(error)
            self.redirect("/?msg-error=1")
        elif code:
            oauth_token_swap(code, callback=add_loop_cb(_on_token_swap))
        else:
            raise tornado.web.HTTPError(404)


class Decrypt(DranoRequestHandler):

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        self.render("decrypt/get.html", user=user)

class ImageExtractor(DranoRequestHandler):

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        self.render("image-extractor/get.html", user=user)


class DecryptComplete(DranoRequestHandler):

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        try:
            message_count = user.data['message_count']
            decrypt_count = user.data['decrypt_count']
            del user.data['decrypt_count']
            del user.data['message_count']
        except KeyError:
            decrypt_count = 0
        self.render("decrypt/complete.html", message_count=message_count,
                    decrypt_count=decrypt_count, user=user)


class Encrypt(DranoRequestHandler):
    """Displays a landing page that handles and displays feedback for
    searching for passwords in the user's gmail account"""

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        self.render("search/get.html", user=user)


class EncryptResults(DranoRequestHandler):
    """Displays the results of searching the "All Messages" Gmail mailboxes
    for passwords"""

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        record_id = user.record_id

        if not record_id:
            self.redirect("/")
        else:
            passwords = user.passwords_for_mailbox(user.all_folder)
            mapping = range(0, passwords.generate_mapping())
            self.render("search/results.html", passwords=passwords,
                        mapping=mapping, user=user)

    @drano.gen.load_user(require=True, refresh=True)
    def post(self, user=None):
        record_id = user.record_id

        if not record_id:
            self.redirect("/")
        else:
            args = self.request.arguments

            try:
                form_action = args['submit_action'][0]
                pws = [v[0] for k, v in args.iteritems() if "token_" in k]

                if len(pws) == 0 or form_action not in ('redact', 'encrypt'):
                    self.redirect("/search/results?msg-info=6")
                else:
                    self.render("search/post.html", user=user,
                                selected_pws=pws, action=form_action)
            except KeyError, IndexError:
                # If the user submitted an expected value to the form (ie
                # they somehow and it didn't include a submit action), then
                # just direct them back to the homepage with an error
                self.redirect('/?msg-error=7')


class AuditWork(DranoRequestHandler):
    """Displays a landing page that handles and displays feedback for
    pricing a user's gmail account"""

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):

        # If we're in a study, store the relevant study parameters as
        # properties on the user object, so we don't have to transmit
        # that state back and forth across the socket connection
        study_name = self.get_secure_cookie('study')
        participant_tag = self.get_secure_cookie('participant_tag')

        if study_name:
            user.data['study_name'] = study_name

        if participant_tag:
            user.data['participant_tag'] = participant_tag

        self.render("audit/get.html", user=user)


class StudyLanding(DranoRequestHandler):
    """General landing page for assigning tracking information to a user
    for use in a 3rd party study"""

    CURRENT_STUDIES = ('audit-response',)

    def get(self, study_tag, participant_tag=False):
        self.clear_all_cookies()
        if study_tag in StudyLanding.CURRENT_STUDIES:
            self.set_secure_cookie('study', study_tag)
            if participant_tag:
                self.set_secure_cookie('participant_tag', participant_tag)
        self.redirect("/")


class Complete(DranoRequestHandler):
    """Displays a wrapping up page, including a survey form to get some
    wrap up results."""

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        record_id = user.record_id
        if not record_id:
            self.redirect("/")
        else:
            self.render("complete/get.html", user=user)

    @drano.gen.load_user()
    def post(self, user=None):
        record_id = user and user.record_id

        if not record_id:
            self.redirect("/")
        else:
            args = self.request.arguments
            # Since we only ask for one of each field value, flatten the
            # args dict into a single key -> value mapping
            form_values = {k: v[0] for k, v in args.items() if len(v) > 0}
            form = survey_form()
            form.populate(form_values)
            if form.validate():
                DB.survey_results(record_id, form.values(),
                                  callback=self._recording_complete)
            else:
                all_errors = []
                for field_name, errors in form.errors().items():
                    all_errors += errors
                self.write(dict(errors=all_errors))
                self.finish()

    def _recording_complete(self, response, error):
        self.write(dict(msg="recording complete"))
        self.finish()


class Logout(DranoRequestHandler):
    """Handle requests to log users out of drano """

    @tornado.web.asynchronous
    def get(self):
        token = self.get_secure_cookie('drano_user')
        email = self.get_secure_cookie('email')

        if token and email:
            drano.users.User.end(email, token, callback=self._complete_logout)
        else:
            self._complete_logout(False)

    def _complete_logout(self, was_logged_out):
        self.clear_all_cookies()
        self.redirect("/?msg-info=5")


class Status(DranoRequestHandler):
    def get(self):
        import tornado.escape
        import drano.users
        current_users = drano.users.User.COLLECTION
        rs = []
        for email in current_users:
            a_user = current_users[email]
            if not a_user.current_work:
                continue
            work = a_user.current_work
            work_start = work.start_time
            values = dict(
                current_work_start=work_start.strftime("%Y-%m-%d %H:%M:%S"),
                current_work=work.work_desc,
                backend=config.port
            )
            rs.append(values)
        self.write(tornado.escape.json_encode(rs))


### Testing Only Methods / Actions ###


class Alter(DranoRequestHandler):

    @drano.gen.load_user()
    def get(self, action, user=None):
        if not user:
            self.write("Not currently logged in as a user")
            self.finish()
        if action == 'expire-oauth':
            user.token_expiration = int(time.time()) - 1
            user.access_token = "fake"
            self.write("Token Invalidated")
            self.finish()
        elif action == "set-transport":
            transport = self.get_argument('transport', None)
            if not transport:
                raise tornado.web.HTTPError(404)
            else:
                self.set_cookie("drano_transport", transport)
                self.write("set {0} as transport".format(transport))
                self.finish()


class Fill(DranoRequestHandler):
    """Request handler for authenticated users for who want to wipe their
    account and populate it with test messages.  This just creates the landing
    page; all the action occurs over socket.io callbacks"""

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        messages = sorted(test_messages())
        self.render("fill/get.html", messages=messages, user=user)


class Touch(DranoRequestHandler):

    @drano.gen.load_user(require=True, refresh=True)
    def get(self, user=None):
        self.render("touch/get.html", user=user)

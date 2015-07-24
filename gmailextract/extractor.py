import os
import config
# import PIL
from PIL import Image
import StringIO
from hashlib import sha256
import hmac
import base64
import pygmail.errors
# from .fs import sanatize_filename, unique_filename
from pygmail.account import Account


ATTACHMENT_MIMES = ('image/jpeg', 'image/png', 'image/gif')


class GmailImageExtractor(object):
    """Image extracting class which handles connecting to gmail on behalf of
    a user over IMAP, extracts images from messages in a Gmail account,
    sends them over websockets to be displayed on a web page, allows users, and
    then syncronizes the messages in the gmail account by deleting the
    images the user selected in the web interface.
    """

    def __init__(self, dest, email, password, limit=None, batch=10, replace=False):
        """
        Args:
            dest     -- the path on the file system where images should be
                        extracted and written to.
            email -- the username of the Gmail account to connect to
            password -- the password of the Gmail account to connect to

        Keyword Args:
            limit   -- an optional limit of the total number of messages to
                       download from the gmail account.
            batch   -- the maximum number of messages to download from Gmail
                       at the same time.
            replace -- whether to rewrite the messages in the Gmail account
                       in place (True) or to just write a second, parallel
                       copy of the altered message and leave the original
                       version alone.

        raise:
            ValueError -- If the given dest path to write extracted images to
                          is not writeable.
        """
        self.dest = dest

        if not self.validate_path():
            raise ValueError("{0} is not a writeable directory".format(dest))

        self.limit = limit
        self.batch = batch
        self.replace = replace
        self.email = email
        self.password = password

    def validate_path(self):
        """Checks to see the currently selected destiation path, for where
        extracted images should be written, is a valid path that we can
        read and write from.

        Return:
            A boolean description of whether the currently selected destination
            is a valid path we can read from and write to.
        """
        if not os.path.isdir(self.dest):
            return False
        elif not os.access(self.dest, os.W_OK):
            return False
        else:
            return True

    def sign_request(self, raw):
        """Takes a predefined secret key and gmail's unique message id concatenated with
        the hash of the image within that message. Sha256 is used for hashing.

        Return:
            An authenticated hash using the specified hmac_key in
            config.py.
        """

        key = config.hmac_key
        self.raw = raw
        hashed = hmac.new(key, raw, sha256)

        return hashed.digest().encode("base64").rstrip('\n')

    def get_resize_img(self, img, img_type, basewidth=100, supported_formats=('jpeg', 'gif',
                                                                              'png')):
        """Constrains proportions of an image object. The max width and support image formats are
        predefined by this function by default.

        Returns:
            A new image with contrained proportions specified by the max basewidth
            """

        img_type = img_type.split("/")[1]

        if img_type in supported_formats:
            buffer = StringIO.StringIO()
            img_object = Image.open(StringIO.StringIO(img))
            wpercent = (basewidth / float(img_object.size[0]))
            hsize = int((float(img_object.size[1]) * float(wpercent)))
            img = img_object.resize((basewidth, hsize), Image.NEAREST)
            format = img_type
            img_object.save(buffer, format)

            return buffer.getvalue()
        else:
            return ""

    def connect(self):
        """Attempts to connect to Gmail using the username and password provided
        at instantiation.

        Returns:
            Returns a boolean description of whether we were able to connect
            to Gmail using the current parameters.
            """

        mail = Account(self.email, password=self.password)
        trash_folder = mail.trash_mailbox()
        if pygmail.errors.is_error(trash_folder):
            return False
        else:
            self.mail = mail
            self.trash_folder = trash_folder
            self.inbox = mail.all_mailbox()
            return True

    def num_messages_with_attachments(self):
        """Checks to see how many Gmail messages have attachments in the
        currently connected gmail account.

        This should only be called after having succesfully connected to Gmail.

        Return:
            The number of messages in the Gmail account that have at least one
            attachment (as advertised by Gmail).
            """

        limit = self.limit if self.limit > 0 else False
        gm_ids = self.inbox.search("has:attachment", gm_ids=True, limit=limit)
        return len(gm_ids)

    def extract(self, callback=None):
        """Extracts images from Gmail messages, encodes them into strings,
        and sends them via websocket to the frontend.

        Keyword Args:
            callback -- An optional function that will be called with updates
            about the image extraction process. If provided,
            will be called with either the following arguments

                        ('image', message id, image id, hmac key)
                        when sending an image via websocket, where
                        `message_id` is the unqiue id of the message,
                        image_id is the unque id of a given image, and
                        hmac key concatenates the message and image id.

                        ('message', first)
                        when fetching messages from Gmail, where `first` is the
                        index of the current message being downloaded.

        Returns:
            The number of images written to disk.
            """

        def _cb(*args):
            if callback:
                callback(*args)

        attachment_count = 0
        num_messages = 0
        offset = 0
        per_page = min(self.batch, self.limit) if self.limit else self.batch
        # Keep track of which attachments belong to which messages.  Do this
        # by keeping track of all attachments downloaded to the filesystem
        # (used as the dict key) and pairing it with two values, the gmail
        # message id and the hash of the attachment (so that we can uniquely
        # identify the attachment again)
        self.mapping = {}
        hit_limit = False
        while True and not hit_limit:
            _cb('message', offset + 1)
            messages = self.inbox.search("has:attachment", full=True,
                                         limit=per_page, offset=offset)
            if len(messages) == 0:
                break

            # STEP 1 - Scan entire inbox for images
            for msg in messages:
                for att in msg.attachments():
                    if att.type in ATTACHMENT_MIMES:

                        # STEP 2 - Note: unique gmail_id for each message
                        msg_id = msg.gmail_id
                        img_identifier = att.sha1()

                        # STEP 3 - Scale down images and encode into base64

                        # Scale down image before encoding
                        img = self.get_resize_img(att.body(), att.type, 100, ('png', 'gif'))
                        if len(img) == 0:  # no img was resized
                            continue

                        # Encode image into base64 format for sending via websocket
                        encoded_img = base64.b64encode(img)

                        # STEP 4 - Build hmac with gmail_id and img_identifier
                        # hmac_req = self.sign_request(msg_id + " " + img_identifier)

                        # STEP 5 - Send message via websockets containing:
                        #          --msg_id: unique id for gmail message
                        #          --image_identifier: hash of image body
                        #          --encoded_img: image in string format encoded
                        #                         in base 64 format
                        #          --hmac: autheticated hash
                        # _cb('image', msg_id, img_identifier, encoded_img, hmac_req)

                        _cb('image', msg_id, img_identifier, encoded_img, msg_id)

                        attachment_count += 1
                        num_messages += 1

                        if self.limit > 0 and num_messages >= self.limit:
                            hit_limit = True
                            break

            offset += per_page

        return attachment_count

    def parse_selected_images(self, selected_images):
        """Take in a dictionary message containing both unique message
        identifiers and unique image identifiers and sorts them. This is
        done because multiple images can be selected for deletion and
        multiple images can be in the same message.

        Returns:
            TODO
            a ....... looking like this.....
            i.e. [[u'12345', u'54312'], [u'12345', u'9879']] becomes
        """

        img_store = {}

        for gmail_id, attachment_hash in selected_images['image']:

            try:
                img_store[gmail_id].append(attachment_hash)
            except KeyError:
                img_store[gmail_id] = [attachment_hash]

        return img_store

    def do_delete(self, gmail_id, attachment_hash):

        label = "Images redacted"

        removed_attachments = 0
        num_attch_removed = 0
        num_msg_changed = 0
        msg_to_change = None

        try:
            msg_to_change = self.inbox.fetch_gm_id(gmail_id, full=True)
        except:
            print "Could not fetch the message with gmail_id ", gmail_id
            return 0, 0

        attach_hashes = {a.sha1(): a for a in msg_to_change.attachments()}
        attach_to_delete = attach_hashes[attachment_hash]

        if attach_to_delete.remove():
            removed_attachments += 1
            num_attch_removed += 1

        if removed_attachments:
            num_msg_changed += 1
            if self.replace:
                msg_to_change.save(self.trash_folder.name, safe_label=label)
            else:
                msg_to_change.save_copy(label)
                return num_attch_removed, num_msg_changed

    def delete(self, msg, label='"Images redacted"', callback=None):
        """Finds image attachments that were downloaded during the
        self.extract() step, and deletes any attachments that were deleted
        from disk from their corresponding images in Gmail.

        Keyword Args:
            label    -- Gmail label to use either as a temporary work label
            (if instatiated with replace=True) or where the altered
            images will be stored (if instatiated with
            replace=False). Note that this label should be in valid
            ATOM string format.
            callback -- An optional funciton that will be called with updates
            about the message update process. If provided,
            will be called with the following sets of arguments:

                        ('fetch', subject, num_attach)
                        Called before fetching a message from gmail. `subject`
                        is the subject of the email message to download, and
                        `num_attach` is the number of attachments to be removed
                        from that message.

                        ('write', subject)
                        Called before writing the altered version of the message
                        back to Gmail.

        Returns:
            Two values, first being the number of attachments that were removed
            from messages in Gmail, and second is the number of messages that
            were altered.
            """

        if len(msg) == 0:
            return 0, 0

        def _cb(*args):
            if callback:
                callback(*args)

        image_bank = []

        try:
            image_bank = self.parse_selected_images(msg)
        except:
            print "Couldn't parse selected images properly"
            return 0, 0

        for gmail_id, attachment_hash in image_bank.iteritems():
            if len(attachment_hash) == 1:
                print gmail_id, attachment_hash
                self.do_delete(gmail_id, attachment_hash)
                print gmail_id, attachment_hash, "deleted"
            elif len(attachment_hash) > 1:
                attachment_hashes = attachment_hash
                for attachment_hash in attachment_hashes:
                    # TODO - use callback to send deleted images info
                    # i.e. num deleted, num changed = do_delete
                    # cb(num deleted, num changed)
                    self.do_delete(gmail_id, attachment_hash)
                    print gmail_id, attachment_hash, "deleted"
            else:  # some bug has occured and no deletions have been executed
                return 0, 0

        return 0, 0

    def check_deletions(self):
        """Checks the filesystem to see which image attachments, downloaded
        in the self.extract() step, have been removed since extraction, and
        thus should be removed from Gmail.

        Returns:
            The number of attachments that have been deleted from the
            filesystem.
            """

        # Now we can find the attachments the user wants removed from their
        # gmail account by finding every file in the mapping that is not
        # still on the file system
        #
        # Here we want to group attachments by gmail_id, so that we only act on
        # a single email message once, instead of pulling it down multiple times
        # (which would change its gmail_id and ruin all things)

        self.to_delete = {}
        self.to_delete_subjects = {}
        self.num_deletions = 0
        for a_name, (gmail_id, a_hash, msg_subject) in self.mapping.items():
            if not os.path.isfile(os.path.join(self.dest, a_name)):
                if gmail_id not in self.to_delete:
                    self.to_delete[gmail_id] = []
                    self.to_delete_subjects[gmail_id] = msg_subject
                    self.to_delete[gmail_id].append(a_hash)
                    self.num_deletions += 1
                    return self.num_deletions

    def sync_old(self, label='"Images redacted"', callback=None):
        """Finds image attachments that were downloaded during the
        self.extract() step, and deletes any attachments that were deleted
        from disk from their corresponding images in Gmail.

        Keyword Args:
            label    -- Gmail label to use either as a temporary work label
            (if instatiated with replace=True) or where the altered
            images will be stored (if instatiated with
            replace=False). Note that this label should be in valid
            ATOM string format.
            callback -- An optional funciton that will be called with updates
            about the message update process. If provided,
            will be called with the following sets of arguments:

                        ('fetch', subject, num_attach)
                        Called before fetching a message from gmail. `subject`
                        is the subject of the email message to download, and
                        `num_attach` is the number of attachments to be removed
                        from that message.

                        ('write', subject)
                        Called before writing the altered version of the message
                        back to Gmail.

        Returns:
            Two values, first being the number of attachments that were removed
            from messages in Gmail, and second is the number of messages that
            were altered.
            """

        # try:
        #    num_to_delete = self.num_deletions
        # except AttributeError:
        #    num_to_delete = self.check_deletions()

        def _cb(*args):
            if callback:
                callback(*args)

        num_msg_changed = 0
        num_attch_removed = 0
        for gmail_id, attch_to_remove in self.to_delete.items():
            msg_sbj = self.to_delete_subjects[gmail_id]

            _cb('fetch', msg_sbj, len(attch_to_remove))
            msg_to_change = self.inbox.fetch_gm_id(gmail_id, full=True)
            attach_hashes = {a.sha1(): a for a in msg_to_change.attachments()}
            removed_attachments = 0
            for attachment_hash in attch_to_remove:
                attach_to_delete = attach_hashes[attachment_hash]
                if attach_to_delete.remove():
                    removed_attachments += 1
                    num_attch_removed += 1

            if removed_attachments:
                num_msg_changed += 1
                _cb('write', msg_sbj)
                if self.replace:
                    msg_to_change.save(self.trash_folder.name, safe_label=label)
                else:
                    msg_to_change.save_copy(label)
                    return num_attch_removed, num_msg_changed

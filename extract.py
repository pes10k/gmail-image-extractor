import os
import sys
import pygmail.account
import pygmail.mailbox
import pygmail.errors
import argparse
from gmailextract.fs import sanatize_filename, unique_filename

parser = argparse.ArgumentParser(description='Extract images from a gmail account.')
parser.add_argument('-e', '--email', type=str, default="",
                    help='The email of the account to search for attachments in.')
parser.add_argument('-p', '--password', type=str, default="",
                    help='The password of the account to search for messages in.')
parser.add_argument('-d', '--dest', type=str, default=".",
                    help="The path where attachments should be downloaded.")
parser.add_argument('-l', '--limit', type=int, default=0,
                    help="The total number of messages that should be downloaded from GMail. Default is 0, or all.")
parser.add_argument('-s', '--simultaneous', type=int, default=10,
                    help="The maximum number of messages that should be downloaded from GMail at a time (defaults to 10).")
parser.add_argument('-w', '--write', action='store_true',
                    help="Edit messages in place instead of saving altered versions with the label 'Images redacted'")
args = parser.parse_args()

# First, do some basic validation and make sure we can write to the given
# directory
if not os.path.isdir(args.dest) :
    print "Error: {0} does not seem to be a directory we can write to".format(args.dest)
    sys.exit()

# Next, see if we can succesfully connect to and select a mailbox from
# Gmail. If not, error out quick
mail = pygmail.account.Account(args.email, password=args.password)
trash_folder = mail.trash_mailbox()
if pygmail.errors.is_error(trash_folder):
    print "Error: Unable to connect to Gmail with provided credentials"
    sys.exit()

# If we're able to connect to Gmail just fine, then we pull down a list of
# all the gmail messages that have attachments in the user's email account
inbox = mail.all_mailbox()
gm_ids = inbox.search("has:attachment", gm_ids=True, limit=args.limit if args.limit > 0 else False)
print "Found {0} messages with attachments".format(len(gm_ids))

attachment_count = 0
num_messages = 0
offset = 0
per_page = min(args.simultaneous, args.limit)
# Keep track of which attachments belong to which messages.  Do this
# by keeping track of all attachments downloaded to the filesystem (used as
# the dict key) and pairing it with two values, the gmail message id and the
# hash of the attachment (so that we can uniquely identify the attachment
# again)
mapping = {}
hit_limit = False
while True and not hit_limit:
    print "Fetching {0} messages starting with message #{1}".format(per_page, offset + 1)
    messages = inbox.search("has:attachment", full=True, limit=per_page, offset=offset)

    if len(messages) == 0:
        break
    for message in messages:
        for attachment in message.attachments():
            if attachment.type in ('image/jpeg', 'image/png', 'image/gif'):
                possible_filename = "{0} - {1}".format(message.subject, attachment.name())
                safe_filename = unique_filename(args.dest, sanatize_filename(possible_filename))

                h = open(os.path.join(args.dest, safe_filename), 'w')
                h.write(attachment.body())
                h.close()
                mapping[safe_filename] = message.gmail_id, attachment.sha1(), message.subject
                attachment_count += 1
        num_messages += 1
        if args.limit > 0 and num_messages >= args.limit:
            hit_limit = True
            break
    offset += per_page

print "Succesfully stored {0} attachments to disk".format(attachment_count)

print "Delete any images you would like to have removed from your Gmail account."
raw_input("Press any key to continue.")

print ""
print "Beginning process of removing images from email messages"

# Now we can find the attachments the user wants removed from their
# gmail account by finding every file in the mapping that is not
# still on the file system
#
# Here we want to group attachments by gmail_id, so that we only act on
# a single email message once, instead of pulling it down multiple times (which
# would change its gmail_id and ruin all things)
to_delete = {}
to_delete_subjects = {}
for attachment_name, (gmail_id, attachment_hash, message_subject) in mapping.items():
    if not os.path.isfile(os.path.join(args.dest, attachment_name)):
        if not gmail_id in to_delete:
            to_delete[gmail_id] = []
            to_delete_subjects[gmail_id] = message_subject
        to_delete[gmail_id].append(attachment_hash)

num_messages_changed = 0
num_attachments_removed = 0
for gmail_id, attachments_to_remove in to_delete.items():
    message_subject = to_delete_subjects[gmail_id]
    print u" - Removing {0} images from message '{1}'".format(len(attachments_to_remove), message_subject)
    message_to_change = inbox.fetch_gm_id(gmail_id, full=True)
    attach_hashes = {a.sha1(): a for a in message_to_change.attachments()}
    removed_attachments = 0
    for attachment_hash in attachments_to_remove:
        attach_to_delete = attach_hashes[attachment_hash]
        if attach_to_delete.remove():
            print u" * Removed {0}".format(attach_to_delete.name())
            removed_attachments += 1
            num_attachments_removed += 1

    if removed_attachments:
        num_messages_changed += 1
        print u" * Writing altered version of message to Gmail"
        if args.write:
            message_to_change.save(trash_folder.name, safe_label='"Images redacted"')
        else:
            message_to_change.save_copy('"Images redacted"')

    print ""

print "Removed {0} images from {1} messages".format(num_attachments_removed, num_messages_changed)

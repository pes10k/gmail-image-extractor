import sys
import argparse
from gmailextract.extractor import GmailImageExtractor

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

extractor = GmailImageExtractor(args.dest, args.email, args.password,
                                limit=args.limit, batch=args.simultaneous,
                                replace=args.write)

# Next, see if we can succesfully connect to and select a mailbox from
# Gmail. If not, error out quick
if not extractor.connect():
    print "Error: Unable to connect to Gmail with provided credentials"
    sys.exit()

# If we're able to connect to Gmail just fine, then we pull down a list of
# all the gmail messages that have attachments in the user's email account
num_messages = extractor.num_messages_with_attachments()
print "Found {0} messages with attachments".format(num_messages)

def _status(*status_args):
    if status_args[0] == 'message':
        print u"Fetching {0} messages starting with {1}".format(args.simultaneous, status_args[1])

attachment_count = extractor.extract(_status)
print "Succesfully stored {0} attachments to disk".format(attachment_count)

print "\n\nDelete any images you would like to have removed from your Gmail account."
raw_input("Press any key to continue.")

print ""
print "Beginning process of removing images from email messages"

num_deletions = extractor.check_deletions()
print "Found {0} images deleted".format(num_deletions)

def _sync_status(*args):
    update_type = args[0]
    if update_type == "fetch":
        print u" - Removing {0} images from message '{1}'".format(args[2], args[1])
    elif update_type == "write":
        print u" * Writing altered version"

num_attch_removed, num_msg_changed = extractor.sync(callback=_sync_status)
print "Removed {0} images from {1} messages".format(num_attch_removed, num_msg_changed)

import tornado
import tornado.web
import tornado.template
import tornado.websocket
import tornado.escape
import os
from os.path import expanduser
from gmailextract.extractor import GmailImageExtractor
import config

root_dir = os.path.dirname(os.path.abspath(__file__))
attr_dir = os.path.join(expanduser("~"), "Gmail Images")
if not os.path.isdir(attr_dir):
    os.mkdir(attr_dir)

tpl_loader = tornado.template.Loader(os.path.join(root_dir, 'templates'))
state = {}


def plural(msg, num):
    if num == 1:
        return msg
    else:
        return u"{0}s".format(msg)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(tpl_loader.load("main.html").generate(home_dir=attr_dir))


class SocketHandler(tornado.websocket.WebSocketHandler):

    def on_message(self, message):
        msg = tornado.escape.json_decode(message)
        if 'type' not in msg:
            return
        elif msg['type'] == 'connect':
            self._handle_connect(msg)
        elif msg['type'] == 'sync':
            self._handle_sync(msg)
        elif msg['type'] == 'confirm':
            self._handle_confirmation(msg)
        elif msg['type'] == 'delete':
            self._handle_delete(msg)
        elif msg['type'] == 'save':
            self._handle_save(msg)
        else:
            return

    def _handle_connect(self, msg, callback=None):

        state['extractor'] = GmailImageExtractor(attr_dir, msg['email'],
                                                 msg['pass'], limit=int(msg['limit']),
                                                 batch=int(msg['simultaneous']),
                                                 replace=bool(msg['rewrite']))
        if not state['extractor'].connect():
            self.write_message({'ok': False,
                                "type": "connect",
                                'msg': u"Unable to connect to Gmail with provided credentials"})
        else:
            self.write_message({'ok': True,
                                "type": "connect",
                                "msg": u"Successfully connecting with Gmail."})

            num_messages = state['extractor'].num_messages_with_attachments()
            self.write_message({'ok': True,
                                "type": "count",
                                "msg": u"Found {0} {1} with attachments"
                                "".format(num_messages, plural(u"message", num_messages)),
                                "num": num_messages})

            def _status(*args):

                if args[0] == 'image':
                    self.write_message({"ok": True,
                                        "type": "image",
                                        "msg_id": args[1],
                                        "img_id": args[2],
                                        "enc_img": args[3],
                                        "hmac_key": args[4]})

                if args[0] == 'message':
                    status_msg = u"Fetching messages {1} - {2}".format(msg['simultaneous'],
                                                                       args[1], num_messages)
                    self.write_message({"ok": True,
                                        "type": "downloading",
                                        "msg": status_msg,
                                        "num": args[1]})

            attachment_count = state['extractor'].extract(_status)
            self.write_message({"ok": True,
                                "type": "download-complete",
                                "msg": "Succesfully found {0} {1}"
                                "".format(attachment_count, plural(u"image", attachment_count)),
                                "num": attachment_count})

    def _handle_delete(self, msg):
        extractor = state['extractor']

        def _delete_status(*args):
            update_type = args[0]

            print(u"Removed {0} out of {1} {2}."
                  "".format(args[1],
                            args[2],
                            plural(u"image", args[2])))

            if update_type == "deleted":
                self.write_message({"ok": True,
                                    "type": "removed",
                                    "msg": u"Removed {0} out of {1} {2}."
                                    "".format(args[1],
                                              args[2],
                                              plural(u"image", args[2]))})

        num_messages_changed, num_images_deleted = extractor.delete(msg, callback=_delete_status)
        self.write_message({"ok": True,
                            "type": "finished",
                            "msg": u"Removed {0} {1} total from {2} {3}."
                            "".format(num_images_deleted,
                                      plural(u"image", num_images_deleted),
                                      num_messages_changed,
                                      plural(u"message", num_messages_changed))})

    def _handle_save(self, msg):
        extractor = state['extractor']

        def _save_status(*args):
            update_type = args[0]
            if update_type == "save-passed":
                self.write_message({"ok": True,
                                    "type": "save",
                                    "file": args[1]})

        extractor.save(msg, _save_status)

    def _handle_sync(self, msg):
        extractor = state['extractor']

        self.write_message({"ok": True,
                            "type": "file-checking",
                            "msg": u"Checking to see which files have been deleted."})
        num_deletions = extractor.check_deletions()
        self.write_message({"ok": True,
                            "type": "file-checked",
                            "msg": u"Found {0} {1} deleted"
                            "".format(num_deletions, plural(u"image", num_deletions)),
                            "num": num_deletions})

    def _handle_confirmation(self, msg):
        extractor = state['extractor']

        def _sync_status(*args):
            update_type = args[0]
            if update_type == "fetch":
                self.write_message({"ok": True,
                                    "type": "removing",
                                    "msg": u"Removing {0} {1} from message '{2}'."
                                    "".format(args[2], args[1], plural(u"image", args[2]))})
            elif update_type == "write":
                self.write_message({"ok": True,
                                    "type": "removed",
                                    "msg": u"Writing altered version of '{0}' to Gmail."
                                    "".format(args[1])})

        num_attch_removed, num_msg_changed = extractor.sync(callback=_sync_status)
        self.write_message({"ok": True,
                            "type": "finished",
                            "msg": u"Removed {0} {1} from {2} {3}."
                            "".format(num_attch_removed,
                                      plural(u"image", num_attch_removed),
                                      num_msg_changed,
                                      plural(u"message", num_msg_changed))})

    def on_close(self):
        state['extractor'] = None

if __name__ == "__main__":
    application = tornado.web.Application([
        (r"/assets/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(root_dir,
                                                                               'assets')}),
        (r'/ws', SocketHandler),
        (r"/", MainHandler),
    ])
    application.listen(config.port)
    tornado.ioloop.IOLoop.instance().start()

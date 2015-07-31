import tornado


def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def io_loop():
    return tornado.ioloop.IOLoop.instance()


def loop_cb(callback):
    io_loop().add_callback(callback)


def loop_cb_args(callback, arg):
    loop_cb(lambda: callback(arg))


def add_loop_cb(callback):
    return lambda arg: loop_cb_args(callback, arg)


def add_loop_cb_args(callback, args, include_return=True):
    if include_return:
        return lambda value: loop_cb(lambda: callback(value, **args))
    else:
        return lambda value: loop_cb(lambda: callback(**args))


def add_loop_cb_mongo_args(callback, args):
    return lambda response, error: loop_cb(lambda: callback(mongo_response=(response, error), **args))


def async_iterate_remote(work, fetch_cb, work_cb, result_cb, complete_cb, req, **kwargs):
    """Handles iterating over items fetched remotely using the Tornado IOLoop

    This function provides an abstraction for iterating over items that
    represent remote resources.

    Args:
        work -- an iterable item of work items to process

    Keyword Args:
        fetch_cb    -- a callback function that will be called once for each item
                       in the passed work variable.  This function must take
                       a named "callback" variable
        work_cb     -- a callback function that will be called with the result of
                       each fetch_cb function.  This function must also take
                       a named "callback" variable
        result_cb   -- a function that will be called once the work_cb function
                       has finished its execution.  This function must also take
                       a named callback variable
        complete_cb -- a callback function that should be called once all the
                       elements in the work set have been processed
        req         -- a drano.errors.WorkRequest instance, that is pushed as
                       an argument to every callback function

        Additional configuration parameters include:
            quick_exit  -- whether or not callback functions can return False
                           to tell the iteration on the current level's elements
                           to top
            context     -- a debugging.DebugContext object to pass to all
                           callback functions, for catching on an exception
    """

    prog = dict(
        wk_item=None,
        wk_count=len(work),
        wk_index=None,
        rs_item=None,
        rs_count=None,
        rs_index=0,
        rs=None
    )

    context = kwargs['context'] if 'context' in kwargs else None
    processing_fetched_item_callback = None

    def _processing_fetched_item_complete(completed_item, work_result):
        loop_cb(lambda: result_cb(prog['wk_item'], completed_item, work_result,
                                  index=prog['rs_index'],
                                  count=prog['rs_count'],
                                  callback=processing_fetched_item_callback,
                                  context=context,
                                  req=req))

    def _process_next_fetched_item(keep_iterating=True):
        prog['rs_index'] = 0 if prog['rs_index'] is None else prog['rs_index'] + 1

        if prog['rs_count'] == prog['rs_index'] or not keep_iterating:
            _process_next_work_unit()
        else:
            prog['rs_item'] = prog['rs'][prog['rs_index']]

            # Function that the work callback will execute to proceed to the
            # next step in the async iteration process (specifically, calling
            # the result callback on the retreived item)
            post_work_callback = lambda work_result: loop_cb(lambda: _processing_fetched_item_complete(prog['rs_item'], work_result))

            loop_cb(lambda: work_cb(prog['wk_item'], prog['rs_item'],
                                    index=prog['rs_index'],
                                    count=prog['rs_count'],
                                    callback=post_work_callback,
                                    context=context,
                                    req=req))

    def _fetched_items(fetched_items):
        # If the client passed False back, it means don't call the result
        # callback any further, or try and process the results. Just advance
        # to the next work item in the set
        if fetched_items is False:
            _process_next_work_unit()
        else:
            try:
                prog['rs_count'] = len(fetched_items)
                prog['rs'] = fetched_items
            except TypeError:
                prog['rs_count'] = 1
                prog['rs'] = (fetched_items,)
            _process_next_fetched_item()

    def _process_next_work_unit():
        prog['rs_index'] = None
        prog['wk_index'] = 0 if prog['wk_index'] is None else prog['wk_index'] + 1

        if prog['wk_count'] == prog['wk_index']:
            # If we're at the last item in the set of work items to process,
            # we're done and we can just call the final, exit, complete callback
            loop_cb(complete_cb)
        else:
            # Otherwise, there is still at least on work item in the set of
            # work items to complete, so execute the "fetch callback" with
            # the current work item to process as an argument"
            prog['wk_item'] = work[prog['wk_index']]
            loop_cb(lambda: fetch_cb(prog['wk_item'],
                                     index=prog['wk_index'],
                                     count=prog['wk_count'],
                                     callback=lambda rs: loop_cb(lambda: _fetched_items(rs)),
                                     context=context,
                                     req=req))

    if 'quick_exit' in kwargs and kwargs['quick_exit']:
        processing_fetched_item_callback = add_loop_cb(_process_next_fetched_item)
    else:
        processing_fetched_item_callback = lambda: loop_cb(_process_next_fetched_item)

    _process_next_work_unit()


def async_iterate(work, work_cb, result_cb, complete_cb, req, current=0, **kwargs):

    count = len(work)
    context = kwargs['context'] if 'context' in kwargs else None

    def _item_completed_callback(item_finished, result, next_time):
        loop_cb(lambda: result_cb(item_finished, result, context=context, req=req))
        if next_time < count:
            work_cb(
                work[next_time],
                callback=lambda rs: loop_cb(lambda: _item_completed_callback(work[next_time], rs, next_time + 1)),
                context=context,
                req=req
            )
        else:
            loop_cb(complete_cb)

    if current < count:
        work_cb(
            work[current],
            callback=lambda rs: loop_cb(lambda: _item_completed_callback(work[current], rs, current + 1)),
            context=context,
            req=req
        )
    else:
        loop_cb(complete_cb)

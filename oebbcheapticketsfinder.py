# -*- coding: utf-8 -*-

import tkinter as tk
import tkinter.ttk as ttk
from threading import Thread, Event
from queue import Queue, PriorityQueue
import time
import datetime
import pickle
import os
import tkcalendar
from oebb import OeBB


class CitySelector(ttk.Combobox):
    def __init__(self, master, oebb, **kwargs):
        super().__init__(master, **kwargs)
        self.stations = []

        def key_pressed(_):
            text = self.get()
            if text:
                try:
                    self.stations = oebb.stations(text)
                    names = [x['name'] if x['name'] else x['meta'] for x in self.stations]
                    self['values'] = names
                except:
                    pass
        self.bind('<Return>', key_pressed)

    def get_station(self):
        cur = self.current()
        if cur == -1:
            return None
        if self.get() != OeBB.station_name(self.stations[cur]):
            return None
        return self.stations[cur]


class QueueItem:
    def __init__(self, priority, data):
        self.priority = priority
        self.data = data

    def __lt__(self, other):
        return self.priority < other.priority


class OeBBCheapTicketsFinder:
    ACTION_NEW_ROUTE = 0
    ACTION_NEW_CONNECTION = 1
    ACTION_FINISHED = 2

    FULL_ROUTE = -1

    class RouteWindow(tk.Toplevel):
        DATE_DAYS = 0
        DATE_FIXED = 1

        TIME_24 = 0
        TIME_FIXED = 1

        def __init__(self, master, queue):
            super().__init__(master)
            self.title('Add route')
            self.protocol('WM_DELETE_WINDOW', self.destroy)
            self.queue = queue
            oebb = OeBB()

            main_frame = tk.Frame(self)
            main_frame.pack(fill=tk.BOTH)

            # ----- Origin and destination selectors -----
            city_frame = tk.Frame(main_frame)
            city_frame.pack(fill=tk.X)

            city_frame_left = tk.Frame(city_frame)
            city_frame_left.pack(side=tk.LEFT, padx=5)
            tk.Label(city_frame_left, text='Origin:').pack(anchor=tk.W)
            city_origin = CitySelector(city_frame_left, oebb)
            city_origin.pack()

            city_frame_right = tk.Frame(city_frame)
            city_frame_right.pack(side=tk.LEFT, padx=5)
            tk.Label(city_frame_right, text='Destination:').pack(anchor=tk.W)
            city_destination = CitySelector(city_frame_right, oebb)
            city_destination.pack()

            # ----- Date selectors -----
            self.date_opt = tk.IntVar()
            date_frame = tk.LabelFrame(main_frame, text='Date')
            date_frame.pack(anchor=tk.W, padx=5)

            date_frame_days = tk.Frame(date_frame)
            date_frame_days.pack(anchor=tk.W)
            tk.Radiobutton(date_frame_days, text='Days', variable=self.date_opt, value=self.DATE_DAYS)\
                .pack(side=tk.LEFT)
            days = ttk.Combobox(date_frame_days, state='readonly', width=5)
            days.pack(side=tk.LEFT, padx=5)
            days['values'] = [str(x) for x in range(1, 31)]
            days.current(0)

            date_frame_fixed = tk.Frame(date_frame)
            date_frame_fixed.pack(anchor=tk.W)
            tk.Radiobutton(date_frame_fixed, text='Fixed', variable=self.date_opt, value=self.DATE_FIXED)\
                .pack(side=tk.LEFT)
            cal_from = tkcalendar.DateEntry(date_frame_fixed, width=10, state='readonly')
            cal_from.pack(padx=3, pady=5, ipady=3, side=tk.LEFT)
            tk.Label(date_frame_fixed, text='-').pack(side=tk.LEFT)
            cal_to = tkcalendar.DateEntry(date_frame_fixed, width=10, state='readonly')
            cal_to.pack(padx=3, pady=5, ipady=3, side=tk.LEFT)

            # Make sure that date interval is always valid (start <= end)
            def date_from_selected(_):
                first = cal_from.get_date()
                second = cal_to.get_date()
                if second < first:
                    cal_to.set_date(first)

            def date_to_selected(_):
                first = cal_from.get_date()
                second = cal_to.get_date()
                if second < first:
                    cal_from.set_date(second)

            cal_from.bind('<<DateEntrySelected>>', date_from_selected)
            cal_to.bind('<<DateEntrySelected>>', date_to_selected)

            # ----- Time selectors -----
            time_frame = tk.LabelFrame(main_frame, text='Time')
            time_frame.pack(anchor=tk.W, padx=5)

            time_from = ttk.Combobox(time_frame, width=6, state='readonly')
            time_from.pack(side=tk.LEFT, padx=3, pady=5)
            self.set_time_values(time_from, 0, 24)
            time_from.current(0)
            tk.Label(time_frame, text='-').pack(side=tk.LEFT)
            time_to = ttk.Combobox(time_frame, width=6, state='readonly')
            time_to.pack(side=tk.LEFT, padx=3, pady=5)
            self.set_time_values(time_to, 1, 25)
            time_to.current(len(time_to['values']) - 1)

            def time_from_selected(_):
                first = int(time_from.get()[:2])
                second = int(time_to.get()[:2])
                self.set_time_values(time_to, first + 1, 25)
                if second <= first:
                    time_to.current(0)

            time_from.bind('<<ComboboxSelected>>', time_from_selected)

            # ----- Confirmation button -----
            def validate():
                city_from = city_origin.get_station()
                city_to = city_destination.get_station()
                if city_from and city_to:
                    _time_to = int(time_to.get()[:2])
                    if _time_to == 24:
                        _time_to = datetime.time.max
                    else:
                        _time_to = datetime.time(hour=_time_to)
                    if self.date_opt.get() == self.DATE_DAYS:
                        dates = datetime.timedelta(days=int(days.get()))
                    else:
                        dates = (cal_from.get_date(), cal_to.get_date())
                    self.queue.put((OeBBCheapTicketsFinder.ACTION_NEW_ROUTE,
                                    {
                                        'stations': (city_from, city_to),
                                        'date': (self.date_opt.get(), dates),
                                        'time': (datetime.time(hour=int(time_from.get()[:2])),
                                                 _time_to)
                                    }))
                    self.destroy()

            ttk.Button(main_frame, text='Confirm', command=validate).pack(pady=5)

        @staticmethod
        def set_time_values(widget, _min, _max):
            widget['values'] = ['%02d:00' % x for x in range(_min, _max)]

    def __init__(self, master=None):
        self.master = master
        self.queue = Queue()
        self.request_queue = PriorityQueue()
        self.routes = {}
        self.best_connections = {}
        self.oebb = OeBB()
        self.stop_thread = None
        self.current_route = None
        self.request_starter_event_id = None

        master.protocol('WM_DELETE_WINDOW', self.on_close)

        if os.path.exists('routes'):
            with open('routes', 'rb') as file:
                routes = pickle.load(file)
                for route in routes:
                    self.queue.put((self.ACTION_NEW_ROUTE, routes[route]))

        main_frame = tk.Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=1)

        # ----- Manual control -----
        manual_frame = tk.Frame(main_frame)
        manual_frame.pack(fill=tk.X)

        # Mode selector
        self.manual = tk.BooleanVar()
        ttk.Checkbutton(manual_frame, text='Manual', variable=self.manual, command=self.change_mode).pack(side=tk.LEFT)

        self.but_frame = tk.Frame(manual_frame)
        self.but_frame.pack(side=tk.LEFT)

        # Manual control buttons
        ttk.Button(self.but_frame, text='Start', command=self.manual_start, state=tk.DISABLED) \
            .pack(side=tk.LEFT, padx=5)
        ttk.Button(self.but_frame, text='Stop', command=self.manual_stop, state=tk.DISABLED) \
            .pack(side=tk.LEFT)

        # ----- Main tree view -----
        tree_columns = [('city_from', 'Origin', 100),
                        ('city_to', 'Destination', 100),
                        ('date_interval', 'Date', 100),
                        ('time_interval', 'Time', 100),
                        ('price', 'Price', 50)]
        self.tree = ttk.Treeview(main_frame, selectmode=tk.BROWSE, heigh=6,
                                 columns=list(map(lambda col: col[0], tree_columns)))
        for col in tree_columns:
            self.tree.heading(col[0], text=col[1])
            self.tree.column(col[0], width=col[2])
        self.tree.column('#0', width=10)
        self.tree.bind('<Delete>', self.delete_selected_route)
        self.tree.pack(fill=tk.BOTH, expand=1)

        # ----- "Add route" button -----
        add_but = ttk.Button(main_frame, text='Add route', command=lambda: self.RouteWindow(master, self.queue))
        add_but.pack()

        # ----- Status bar -----
        self.status = tk.StringVar()
        tk.Label(main_frame, textvariable=self.status, bd=1, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X)
        self.status.set('Waiting for task')

        self.master.after(200, self.event_loop)
        self.request_starter_event_id = self.master.after(1000, self.request_starter)
        self.master.after(60000, self.delete_old_connections)

    def process_route(self, item):
        """Retrieve connections that satisfies route restrictions."""
        last_date = item['last_date']
        last_req = 0
        i = 0
        while True:
            if item['exit'].is_set():
                if item['iter_limit'] != self.FULL_ROUTE:
                    item['last_date'] = last_date
                    self.request_queue.put(QueueItem(datetime.datetime.now(), item))
                self.queue.put((self.ACTION_FINISHED, item['oebb']))
                return
            # Get connections
            sleep_time = 1
            while True:
                next_date = self.next_valid_date(last_date, item['route'])
                try:
                    if i == 0 or next_date != last_date or (time.time() - last_req) > 2300:
                        connections = item['oebb'].connections(item['route']['stations'][0],
                                                               item['route']['stations'][1],
                                                               next_date)
                    else:
                        connections = item['oebb'].next_connections(connections[-1])
                    last_req = time.time()
                    break
                except Exception as _:
                    time.sleep(sleep_time)
                    sleep_time = min(sleep_time + 1, 30)

            # Get prices
            sleep_time = 1
            while True:
                try:
                    prices = item['oebb'].prices(connections)
                    break
                except:
                    time.sleep(sleep_time)
                    sleep_time = min(sleep_time + 1, 30)

            for index, connection in enumerate(connections):
                con_datetime = OeBB.get_datetime(connection['from']['departure'])
                if self.check_date(con_datetime, item['route']):
                    self.queue.put((self.ACTION_NEW_CONNECTION,
                                    {
                                        'connection': connection,
                                        'price': prices[index],
                                        'route_id': item['route_id']
                                    }))
            if len(connections) == 0 or \
               self.next_valid_date(OeBB.get_datetime(connections[-1]['from']['departure']), item['route']) is None:
                if item['iter_limit'] != self.FULL_ROUTE:
                    item['last_date'] = None
                    self.request_queue.put(QueueItem(datetime.datetime.now() + datetime.timedelta(minutes=30),
                                                     item))
                item['exit'].set()
                self.queue.put((self.ACTION_FINISHED, item['oebb']))
                return
            last_date = OeBB.get_datetime(connections[-1]['from']['departure'])
            time.sleep(3)
            i += 1
            if item['iter_limit'] != self.FULL_ROUTE and i == item['iter_limit']:
                break
        if item['iter_limit'] != self.FULL_ROUTE:
            item['last_date'] = last_date
            self.request_queue.put(QueueItem(datetime.datetime.now() + datetime.timedelta(minutes=10),
                                             item))
        item['exit'].set()
        self.queue.put((self.ACTION_FINISHED, item['oebb']))

    @classmethod
    def get_date_interval(cls, route, now=datetime.datetime.now().date()):
        """Return route date interval."""
        if route['date'][0] == cls.RouteWindow.DATE_DAYS:
            date_from = now
            date_to = now + route['date'][1]
        else:
            date_from = max(route['date'][1][0], now)
            date_to = route['date'][1][1]
        return date_from, date_to

    @classmethod
    def check_date(cls, cur_datetime, route):
        """Check if date satisfies route constraints."""
        cur_time = cur_datetime.time()
        if not(route['time'][0] <= cur_time <= route['time'][1]):
            return False
        cur_date = cur_datetime.date()
        date_from, date_to = cls.get_date_interval(route)
        if not(date_from <= cur_date <= date_to):
            return False
        return True

    @classmethod
    def next_valid_date(cls, cur_datetime, route):
        """Return next valid date.

        Get route and datetime object as input. If datetime satisfies route
        conditions, return it. Otherwise return next date that satisfies
        route conditions, or None if such not exists.
        """
        if cur_datetime is None:
            cur_datetime = datetime.datetime.now()
        cur_date = cur_datetime.date()
        cur_time = cur_datetime.time()
        if cur_time < route['time'][0]:
            cur_time = route['time'][0]
        elif cur_time > route['time'][1]:
            cur_time = route['time'][0]
            cur_date = cur_date + datetime.timedelta(days=1)
        date_from, date_to = cls.get_date_interval(route)
        if cur_date > date_to:
            return None
        elif cur_date < date_from:
            cur_date = date_from
            cur_time = route['time'][0]

        return datetime.datetime.combine(cur_date, cur_time)

    def update_connections(self, route_id):
        """Update route connections in treeview."""
        if not self.tree.exists(route_id):
            return
        items = self.tree.get_children(item=route_id)
        for item in items:
            self.tree.delete(item)
        for connection in self.best_connections[route_id][:5]:
            con_datetime = OeBB.get_datetime(connection['connection']['from']['departure'])
            self.tree.insert(route_id, 'end', values=['', '',
                                                      con_datetime.strftime('%d/%m/%Y'),
                                                      con_datetime.strftime('%H:%M'),
                                                      connection['price']['price']])

    def insert_connection(self, item):
        """Add or update connection and update treeview if needed."""
        # Check if connection already in the list
        for index, connection in enumerate(self.best_connections[item['route_id']]):
            if item['connection']['from']['departure'] == connection['connection']['from']['departure'] and \
               item['connection']['to']['arrival'] == connection['connection']['to']['arrival']:
                if 'price' not in item['price']:
                    del self.best_connections[item['route_id']][index]
                    self.update_connections(item['route_id'])
                    break
                if item['price']['price'] != connection['price']['price']:
                    self.best_connections[item['route_id']][index] = item
                    self.best_connections[item['route_id']].sort(key=lambda x: x['price']['price'])
                    self.update_connections(item['route_id'])
                break
        else:  # Connection not in the list
            # Insert new connection
            if 'price' not in item['price']:
                return
            ls_len = len(self.best_connections[item['route_id']])
            last_shown = self.best_connections[item['route_id']][4] if ls_len >= 5 else None
            self.best_connections[item['route_id']].append(item)
            self.best_connections[item['route_id']].sort(key=lambda x: x['price']['price'])

            if last_shown is None:
                self.update_connections(item['route_id'])
            else:
                if ls_len >= 10:
                    self.best_connections[item['route_id']].pop()
                if self.best_connections[item['route_id']][4] != last_shown:
                    self.update_connections(item['route_id'])

    def delete_old_connections(self):
        """Delete expired connections and update treeview."""
        now = datetime.datetime.now()
        for route in self.routes:
            con_len = len(self.best_connections[route])
            last_shown = self.best_connections[route][4] if con_len >= 5 else None
            self.best_connections[route][:] = [con for con in self.best_connections[route]
                                               if OeBB.get_datetime(con['connection']['from']['departure']) > now]
            con_len_new = len(self.best_connections[route])
            if con_len != con_len_new:
                if con_len_new < 5:
                    self.update_connections(route)
                elif last_shown != self.best_connections[route][4]:
                    self.update_connections(route)

        self.master.after(60000, self.delete_old_connections)

    def delete_selected_route(self, _):
        """Delete route if selected."""
        cur_item = self.tree.focus()
        if cur_item in self.tree.get_children():
            del self.routes[cur_item]
            del self.best_connections[cur_item]
            self.tree.delete(cur_item)
            if self.current_route == cur_item:
                self.stop_thread.set()
                self.stop_thread = None
                self.current_route = None
                self.queue.put((self.ACTION_FINISHED, None))

    def change_mode(self):
        """Change current working mode."""
        if self.manual.get():
            if self.stop_thread is not None:
                self.stop_thread.set()
                self.stop_thread = None
                self.current_route = None
            if self.request_starter_event_id is not None:
                self.master.after_cancel(self.request_starter_event_id)
            self.status.set('Select task')
            for wid in self.but_frame.winfo_children():
                wid['state'] = tk.NORMAL
        else:
            for wid in self.but_frame.winfo_children():
                wid['state'] = tk.DISABLED
            self.request_starter()

    def manual_start(self):
        """Start route processing in manual mode."""
        self.manual_stop()
        cur_item = self.tree.focus()
        if cur_item in self.tree.get_children():
            item = {'route': self.routes[cur_item],
                    'route_id': cur_item,
                    'last_date': None}
            if self.oebb is None:
                item['oebb'] = OeBB()
            else:
                item['oebb'] = self.oebb
                self.oebb = None

            self.stop_thread = Event()
            item['exit'] = self.stop_thread
            item['iter_limit'] = self.FULL_ROUTE

            thread = Thread(target=self.process_route,
                            args=(item,),
                            daemon=True)
            thread.start()
            self.current_route = item['route_id']
            self.request_starter_event_id = None
            self.status.set('Processing: ' + OeBB.station_name(item['route']['stations'][0]) +
                            ' - ' + OeBB.station_name(item['route']['stations'][1]))

    def manual_stop(self):
        """Stop route processing in manual mode."""
        if self.current_route is not None:
            if self.stop_thread is not None:
                self.stop_thread.set()
                self.stop_thread = None
            self.current_route = None
            self.status.set('Select task')

    def request_starter(self):
        """Check if next route should be processed.

        Check if time has come to get connections of the next route in queue
        and spawn new thread.
        """
        while not self.request_queue.empty():
            item = self.request_queue.get()
            if item.data['route_id'] in self.routes:
                break
        else:
            self.request_starter_event_id = self.master.after(1000, self.request_starter)
            self.status.set('Task queue is empty')
            return

        if item.priority > datetime.datetime.now():
            self.request_queue.put(item)
            self.request_starter_event_id = self.master.after(1000, self.request_starter)
            self.status.set('Next check at ' + item.priority.strftime('%H:%M'))
            return

        if self.oebb is None:
            item.data['oebb'] = OeBB()
        else:
            item.data['oebb'] = self.oebb
            self.oebb = None

        self.stop_thread = Event()
        item.data['exit'] = self.stop_thread
        item.data['iter_limit'] = 20

        thread = Thread(target=self.process_route,
                        args=(item.data, ),
                        daemon=True)
        thread.start()
        self.current_route = item.data['route_id']
        self.request_starter_event_id = None
        self.status.set('Processing: ' + OeBB.station_name(item.data['route']['stations'][0]) +
                        ' - ' + OeBB.station_name(item.data['route']['stations'][1]))

    def event_loop(self):
        """Process events in queue."""
        while not self.queue.empty():
            ev_type, ev = self.queue.get()

            if ev_type == self.ACTION_NEW_ROUTE:
                if ev['date'][0] == self.RouteWindow.DATE_DAYS:
                    date_interval = 'Next %s day(s)' % ev['date'][1].days
                else:
                    date_interval = ev['date'][1][0].strftime('%d/%m/%Y')
                    if ev['date'][1][0] != ev['date'][1][1]:
                        date_interval += ev['date'][1][1].strftime(' - %d/%m/%Y')
                if ev['time'][0] == datetime.time.min and ev['time'][1] == datetime.time.max:
                    time_interval = ''
                else:
                    time_interval = ev['time'][0].strftime('%H') + ' - ' + ev['time'][1].strftime('%H')
                route_id = self.tree.insert('', 'end', values=[OeBB.station_name(ev['stations'][0]),
                                                               OeBB.station_name(ev['stations'][1]),
                                                               date_interval,
                                                               time_interval])
                self.routes[route_id] = ev
                self.best_connections[route_id] = []
                self.request_queue.put(QueueItem(datetime.datetime.now(),
                                                 {
                                                     'route': ev,
                                                     'route_id': route_id,
                                                     'last_date': None
                                                 }))

            elif ev_type == self.ACTION_NEW_CONNECTION:
                if 'reducedScope' not in ev['price'] and ev['route_id'] in self.routes:
                    self.insert_connection(ev)

            elif ev_type == self.ACTION_FINISHED:
                if self.oebb is None:
                    self.oebb = ev
                if self.manual.get():
                    if self.current_route is None:
                        self.status.set('Select task')
                elif self.request_starter_event_id is None and (self.stop_thread is None or self.stop_thread.is_set()):
                    self.current_route = None
                    self.request_starter_event_id = self.master.after(30000, self.request_starter)
                    self.status.set('Cooldown')

        self.master.after(200, self.event_loop)

    def on_close(self):
        """Save routes and destroy window."""
        with open('routes', 'wb') as file:
            pickle.dump(self.routes, file)
        self.master.destroy()


if __name__ == '__main__':
    if 'PYCHARM_HOSTED' not in os.environ:
        import sys
        sys.stderr = open('error.log', 'a')

    root = tk.Tk()
    app = OeBBCheapTicketsFinder(root)
    root.title('ÖBB Cheap Tickets Finder')
    root.mainloop()

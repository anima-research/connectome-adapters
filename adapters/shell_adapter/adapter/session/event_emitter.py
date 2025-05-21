class EventEmitter:
    def __init__(self):
        self.listeners = {}

    def on(self, event_name, callback):
        """Register an event listener"""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def off(self, event_name, callback):
        """Remove an event listener"""
        if event_name in self.listeners and callback in self.listeners[event_name]:
            self.listeners[event_name].remove(callback)

    async def emit(self, event_name, *args, **kwargs):
        """Emit an event to all listeners"""
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                await callback(*args, **kwargs)

Minimal copies of the Paper API types BuildBridge uses, with the same kinds (class, interface, enum)
and method signatures as the real API. They let the fake server in ../fake-server compile and run the
real plugin code without the Paper jar. The release build compiles against the real paper-api.

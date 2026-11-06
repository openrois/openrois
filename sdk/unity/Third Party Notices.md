# Third Party Notices

This package bundles the third-party assemblies below in `Runtime/Plugins`, unmodified,
as `System.Text.Json` and its dependencies. `scripts~/bundle_dlls.py` restores them from
NuGet at the version that `interfaces/csharp` pins.

| Component | Version | Source | License |
|-----------|---------|--------|---------|
| System.Text.Json | 8.0.6 | <https://www.nuget.org/packages/System.Text.Json/8.0.6> | MIT |
| System.Text.Encodings.Web | 8.0.0 | <https://www.nuget.org/packages/System.Text.Encodings.Web/8.0.0> | MIT |
| Microsoft.Bcl.AsyncInterfaces | 8.0.0 | <https://www.nuget.org/packages/Microsoft.Bcl.AsyncInterfaces/8.0.0> | MIT |
| System.Runtime.CompilerServices.Unsafe | 6.0.0 | <https://www.nuget.org/packages/System.Runtime.CompilerServices.Unsafe/6.0.0> | MIT |

All four come from the [.NET runtime repository](https://github.com/dotnet/runtime), which
lists the code it incorporates in its
[third-party notices](https://github.com/dotnet/runtime/blob/release/8.0/THIRD-PARTY-NOTICES.TXT).
Each NuGet package carries the same license text:

```text
The MIT License (MIT)

Copyright (c) .NET Foundation and Contributors

All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

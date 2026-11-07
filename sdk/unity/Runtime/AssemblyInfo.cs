using System.Runtime.CompilerServices;

// The Editor assembly ends every client when Play Mode ends, which is not a
// call for an application to make.
[assembly: InternalsVisibleTo("OpenRoIS.Sdk.Editor")]

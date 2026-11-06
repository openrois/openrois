using System.Linq;
using OpenRoIS.Interfaces.Profiles;

namespace OpenRoIS.Interfaces
{
    /// <summary>
    /// Builds the filter text of every <c>condition</c> parameter, with correct quoting.
    /// </summary>
    /// <remarks>
    /// Hand-written, not generated: JSON Schema describes data, not functions. This class
    /// mirrors the builders of the Python module <c>openrois.interfaces.condition</c> and
    /// the TypeScript module <c>condition.ts</c>. It has no parser, because only an engine
    /// reads a condition. Section 17.4 of docs/rois-reference.md describes the language.
    /// </remarks>
    public static class Condition
    {
        /// <summary>The property that selects a component by its fully qualified ref.</summary>
        public const string ComponentRefProperty = "component_ref";

        /// <summary>The property that selects components by the URN of their profile identifier.</summary>
        public const string ComponentTypeProperty = "component_type";

        /// <summary>Writes <paramref name="value"/> as a CQL2 string literal, doubling any single quote.</summary>
        public static string Quote(string value)
        {
            return "'" + value.Replace("'", "''") + "'";
        }

        /// <summary>Builds <c>property = 'value'</c>.</summary>
        public static string Eq(string propertyName, string value)
        {
            return $"{propertyName} = {Quote(value)}";
        }

        /// <summary>Builds <c>property LIKE 'pattern'</c>. The pattern keeps its wildcards.</summary>
        public static string Like(string propertyName, string pattern)
        {
            return $"{propertyName} LIKE {Quote(pattern)}";
        }

        /// <summary>Joins conditions with AND, skipping empty ones.</summary>
        /// <remarks>
        /// A condition is empty here when <see cref="string.IsNullOrWhiteSpace(string)"/> holds
        /// for it, and the other languages define empty differently. U+0085 is empty here and
        /// in Python, not in TypeScript. U+FEFF is empty in TypeScript only. U+001C to U+001F
        /// are empty in Python only. interfaces/fixtures/value-edges.json records these cases.
        /// </remarks>
        public static string AllOf(params string[] conditions)
        {
            return string.Join(" AND ", conditions.Where(condition => !string.IsNullOrWhiteSpace(condition)));
        }

        /// <summary>Selects the one component with this fully qualified ref, such as <c>reachy_real/head</c>.</summary>
        public static string ComponentRef(string reference)
        {
            return Eq(ComponentRefProperty, reference);
        }

        /// <summary>
        /// The <c>component_type</c> value of a component profile identifier, for example
        /// <c>urn:x-rois:def:component:OMG::PersonDetection</c>, the form the component
        /// profiles of the specification use.
        /// </summary>
        public static string ComponentTypeUrn(RoISIdentifierType identifier)
        {
            return $"urn:x-rois:def:component:{identifier.Authority}::{identifier.Code}";
        }

        /// <summary>Selects every component of a type.</summary>
        public static string ComponentType(RoISIdentifierType identifier)
        {
            return Eq(ComponentTypeProperty, ComponentTypeUrn(identifier));
        }
    }
}

// Offscreen WPF hit testing of production resources and the actual building footer; no Builder startup.
using System.IO;
using System.Globalization;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Xml.Linq;

static class Program
{
    static readonly XNamespace Presentation = "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
    static readonly XNamespace Xaml = "http://schemas.microsoft.com/winfx/2006/xaml";

    static string Owner(DependencyObject? item, ToggleButton show, Button cancel)
    {
        for (; item != null; item = VisualTreeHelper.GetParent(item))
        {
            if (ReferenceEquals(item, show)) return "ShowLog";
            if (ReferenceEquals(item, cancel)) return "CancelButton";
        }
        return "neither-control";
    }

    static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            Require(args.Length == 2, "expected source snapshot and output directory");
            string source = args[0], output = args[1];
            Directory.CreateDirectory(output);
            var appXml = XDocument.Load(Path.Combine(source, "App.xaml"));
            var resources = appXml.Root?.Element(Presentation + "Application.Resources")
                ?? throw new InvalidDataException("production application resources not found");
            var dictionary = new XElement(Presentation + "ResourceDictionary",
                new XAttribute(XNamespace.Xmlns + "x", Xaml.NamespaceName),
                resources.Elements().Select(value => new XElement(value)));
            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            app.Resources = (ResourceDictionary)XamlReader.Parse(dictionary.ToString());
            var main = XDocument.Load(Path.Combine(source, "MainWindow.xaml"));
            var showXml = main.Descendants(Presentation + "ToggleButton")
                .Single(element => (string?)element.Attribute(Xaml + "Name") == "ShowLog");
            var barXml = new XElement(showXml.Parent ?? throw new InvalidDataException("ShowLog has no parent"));
            Require(barXml.Name == Presentation + "Grid", "production footer changed shape");
            barXml.SetAttributeValue(XNamespace.Xmlns + "x", Xaml.NamespaceName);
            var knownEvents = new[] { ("ShowLog", "Checked", "LogToggled"), ("ShowLog", "Unchecked", "LogToggled"),
                                      ("CancelButton", "Click", "CancelBuild") };
            foreach (var (name, attribute, handler) in knownEvents)
            {
                var element = barXml.Descendants().Single(value => (string?)value.Attribute(Xaml + "Name") == name);
                Require((string?)element.Attribute(attribute) == handler, "known event boundary changed: " + name + "." + attribute);
                element.Attribute(attribute)!.Remove();
            }
            File.WriteAllText(Path.Combine(output, "extracted-resources.xaml"), dictionary.ToString());
            File.WriteAllText(Path.Combine(output, "extracted-footer.xaml"), barXml.ToString());
            var metrics = new List<object>();
            int defects = 0, controls = 0;
            foreach (double width in new[] { 600.0, 900.0 })
            {
                var bar = (Grid)XamlReader.Parse(barXml.ToString());
                var surface = new Border { Background = (Brush)app.Resources["Page"], Child = bar };
                surface.Measure(new Size(width, double.PositiveInfinity));
                surface.Arrange(new Rect(0, 0, width, surface.DesiredSize.Height));
                surface.UpdateLayout();
                var show = (ToggleButton)bar.FindName("ShowLog");
                var cancel = (Button)bar.FindName("CancelButton");
                show.ApplyTemplate(); cancel.ApplyTemplate(); surface.UpdateLayout();
                var bitmap = new RenderTargetBitmap((int)Math.Ceiling(width), (int)Math.Ceiling(surface.ActualHeight),
                    96, 96, PixelFormats.Pbgra32);
                bitmap.Render(surface);
                var encoder = new PngBitmapEncoder();
                encoder.Frames.Add(BitmapFrame.Create(bitmap));
                using (var stream = File.Create(Path.Combine(output, "footer-" + width.ToString(CultureInfo.InvariantCulture) + ".png"))) encoder.Save(stream);
                var origin = show.TranslatePoint(new Point(0, 0), bar);
                var cancelOrigin = cancel.TranslatePoint(new Point(0, 0), bar);
                var label = new FormattedText(show.Content.ToString() ?? "", show.Language.GetSpecificCulture(), show.FlowDirection,
                    new Typeface(show.FontFamily, show.FontStyle, show.FontWeight, show.FontStretch), show.FontSize,
                    show.Foreground, VisualTreeHelper.GetDpi(surface).PixelsPerDip);
                var labelPoint = new Point(origin.X + label.WidthIncludingTrailingWhitespace / 2, origin.Y + show.ActualHeight / 2);
                double blankStart = origin.X + Math.Max(label.WidthIncludingTrailingWhitespace, show.DesiredSize.Width) + 16;
                double blankEnd = cancelOrigin.X - 16;
                Require(blankEnd > blankStart, "authored width has no substantial blank column space");
                var blankPoint = new Point((blankStart + blankEnd) / 2, labelPoint.Y);
                var cancelPoint = new Point(cancelOrigin.X + cancel.ActualWidth / 2, cancelOrigin.Y + cancel.ActualHeight / 2);
                string labelOwner = Owner(VisualTreeHelper.HitTest(bar, labelPoint)?.VisualHit, show, cancel);
                string blankOwner = Owner(VisualTreeHelper.HitTest(bar, blankPoint)?.VisualHit, show, cancel);
                string cancelOwner = Owner(VisualTreeHelper.HitTest(bar, cancelPoint)?.VisualHit, show, cancel);
                Require(labelOwner == "ShowLog", "label positive control failed: " + labelOwner);
                Require(cancelOwner == "CancelButton", "Cancel positive control failed: " + cancelOwner);
                controls += 2;
                bool desiredBlankBehavior = blankOwner != "ShowLog";
                if (!desiredBlankBehavior) defects++;
                metrics.Add(new {
                    availableWidth = width, height = surface.ActualHeight, showDesiredWidth = show.DesiredSize.Width,
                    showActualWidth = show.ActualWidth, firstColumnWidth = bar.ColumnDefinitions[0].ActualWidth,
                    labelGlyphWidth = label.WidthIncludingTrailingWhitespace, cancelWidth = cancel.ActualWidth,
                    horizontalAlignmentDiagnostic = show.HorizontalAlignment.ToString(),
                    labelPoint = new { x = labelPoint.X, y = labelPoint.Y }, labelOwner,
                    blankPoint = new { x = blankPoint.X, y = blankPoint.Y }, blankOwner,
                    cancelPoint = new { x = cancelPoint.X, y = cancelPoint.Y }, cancelOwner,
                    blankPointBeyondLabel = blankPoint.X > origin.X + label.WidthIncludingTrailingWhitespace + 16,
                    desiredBlankBehavior, png = "footer-" + width.ToString(CultureInfo.InvariantCulture) + ".png"
                });
                Console.WriteLine($"width={width}: label->{labelOwner}, blank->{blankOwner}, Cancel->{cancelOwner}; label={label.WidthIncludingTrailingWhitespace:F2}, toggle={show.ActualWidth:F2}");
            }
            var result = new {
                status = defects == 0 ? "pass" : "fail",
                negativeBlankExpectationsFailed = defects, positiveControlsPassed = controls, metrics,
                knownEventsRemoved = knownEvents.Select(value => value.Item1 + "." + value.Item2 + "=" + value.Item3).ToArray(),
                boundaries = "Only production Application.Resources and the exact ShowLog parent Grid are instantiated. No actual Builder/App/MainWindow class, StartupUri, network, window Show, OS input, or alignment correction. A zero-padding host supplies width/background only."
            };
            File.WriteAllText(Path.Combine(output, "hitbox-result.json"), JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine(JsonSerializer.Serialize(result));
            Console.WriteLine($"Builder details hitbox: 6 checks, {defects} failed (4 positive controls, 2 blank-space expectations).");
            return defects == 0 ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 2;
        }
    }
}

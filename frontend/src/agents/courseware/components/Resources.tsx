import SharedResources, {
  type ResourcesProps,
} from "../../../components/Resources";

export default function Resources(
  props: Omit<ResourcesProps, "libraryPath" | "productName">,
) {
  return (
    <SharedResources
      {...props}
      libraryPath="/courseware"
      productName="互动课件"
    />
  );
}

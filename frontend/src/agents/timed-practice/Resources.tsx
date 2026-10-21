import SharedResources, {
  type ResourcesProps,
} from "../../components/Resources";

export default function Resources(
  props: Omit<ResourcesProps, "libraryPath" | "productName">,
) {
  return (
    <SharedResources
      {...props}
      libraryPath="/timed-practice"
      productName="限时练习"
    />
  );
}

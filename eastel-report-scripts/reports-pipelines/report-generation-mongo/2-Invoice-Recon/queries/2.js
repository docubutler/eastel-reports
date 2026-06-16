/*
Query 2: Domestic MO SMS total count.

Output:
{
  service_type: "SMS",
  charge_type: "MO",
  sms_type: "On Net / Off Net",
  total: 4863
}
*/

db.{{request_log}}.aggregate([
  {
    $group: {
      _id: null,
      total: {
        $sum: {
          $cond: [
            {
              $and: [
                { $gte: ["$req_time", ISODate("{{start_date}}")] },
                { $lt: ["$req_time", ISODate("{{end_date}}")] },
                { $eq: ["$rat_type", "SM"] },
                { $eq: ["$service_type_sub_cd", "MO"] },
                { $eq: ["$roaming_destination_id", 87] }
              ]
            },
            1,
            0
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "SMS" },
      charge_type: { $literal: "MO" },
      sms_type: { $literal: "On Net / Off Net" },
      total: 1
    }
  }
]);
